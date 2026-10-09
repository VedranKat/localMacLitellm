// One fixed launchd entry manages PostgreSQL and LiteLLM as _litellm.
// No caller-supplied paths or arguments are accepted by the installed binary.
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

static volatile sig_atomic_t stopping = 0;
static void stop_signal(int number) { (void)number; stopping = 1; }
static void child_signal(int number) { (void)number; }
static double now(void) {
    struct timespec value;
    if (clock_gettime(CLOCK_MONOTONIC, &value)) return 0;
    return (double)value.tv_sec + value.tv_nsec / 1000000000.0;
}
static void pause_briefly(void) {
    struct timespec delay = {0, 100000000};
    nanosleep(&delay, NULL);
}
static pid_t start_child(const char *executable, char *const arguments[], const char *log_path) {
    pid_t pid = fork();
    if (pid == 0) {
        if (setpgid(0, 0)) _exit(111);
        struct sigaction action = {0};
        action.sa_handler = SIG_DFL;
        sigemptyset(&action.sa_mask);
        sigaction(SIGTERM, &action, NULL);
        sigaction(SIGINT, &action, NULL);
        int fd = open(log_path, O_WRONLY | O_APPEND | O_CREAT | O_NOFOLLOW, 0600);
        if (fd < 0 || dup2(fd, 1) < 0 || dup2(fd, 2) < 0) _exit(111);
        if (fd > 2) close(fd);
        execv(executable, arguments);
        _exit(111);
    }
    if (pid > 0 && setpgid(pid, pid) && errno != EACCES && errno != ESRCH) {
        kill(pid, SIGKILL);
        while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {}
        return -1;
    }
    return pid;
}
static int reaped(pid_t pid) {
    int status;
    pid_t result = waitpid(pid, &status, WNOHANG);
    return result == pid || (result < 0 && errno == ECHILD);
}
static void signal_group(pid_t pid, int number) {
    if (pid <= 0) return;
    kill(-pid, number);
}
static void stop_child(pid_t pid, int database) {
    if (pid <= 0) return;
    if (reaped(pid)) {
        if (!database) signal_group(pid, SIGKILL);
        return;
    }
    // Signal the PostgreSQL parent, which coordinates shutdown of its workers.
    if (database) kill(pid, SIGTERM);
    else signal_group(pid, SIGTERM);
    double deadline = now() + 20;
    while (!reaped(pid) && now() < deadline) pause_briefly();
    if (reaped(pid)) {
        if (!database) signal_group(pid, SIGKILL);
        return;
    }
    if (database) kill(pid, SIGINT);
    else signal_group(pid, SIGKILL);
    deadline = now() + (database ? 20 : 2);
    while (!reaped(pid) && now() < deadline) pause_briefly();
    if (!database) signal_group(pid, SIGKILL);
    if (!reaped(pid)) {
        signal_group(pid, SIGKILL);
        while (waitpid(pid, NULL, 0) < 0 && errno == EINTR) {}
    }
}
int main(int argc, char **argv) {
    (void)argv;
    if (argc != 1) {
        fputs("LiteLLM Gateway accepts no arguments.\n", stderr); return 2;
    }
#ifdef SUPERVISOR_TEST
    // Only the disposable unprivileged test binary contains these overrides.
    const char *database_executable = getenv("FIXTURE_DATABASE");
    const char *gateway_executable = getenv("FIXTURE_GATEWAY");
    const char *database_data = getenv("FIXTURE_DATA");
    const char *gateway_script = getenv("FIXTURE_SCRIPT");
    const char *database_log = getenv("FIXTURE_DATABASE_LOG");
    const char *gateway_log = getenv("FIXTURE_GATEWAY_LOG");
    if (!database_executable || !gateway_executable || !database_data || !gateway_script || !database_log || !gateway_log) return 2;
#else
    if (geteuid() == 0 || geteuid() >= 500) {
        fputs("LiteLLM Gateway must run as its dedicated service account.\n", stderr); return 2;
    }
    const char *database_executable = "/Library/Application Support/LiteLLM/runtime/postgres/bin/postgres";
    const char *gateway_executable = "/Library/Application Support/LiteLLM/runtime/python/bin/python3.12";
    const char *database_data = "/Library/Application Support/LiteLLM/state/postgres";
    const char *gateway_script = "/Library/Application Support/LiteLLM/libexec/gateway.py";
    const char *database_log = "/Library/Application Support/LiteLLM/logs/postgres.log";
    const char *gateway_log = "/Library/Application Support/LiteLLM/logs/gateway.log";
#endif
    umask(077);
    struct sigaction action = {0};
    action.sa_handler = stop_signal;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGTERM, &action, NULL) || sigaction(SIGINT, &action, NULL)) return 1;
    action.sa_handler = child_signal;
    if (sigaction(SIGCHLD, &action, NULL)) return 1;
    char *database_arguments[] = {(char *)database_executable, "-D", (char *)database_data, NULL};
    char *gateway_arguments[] = {(char *)gateway_executable, "-I", (char *)gateway_script, NULL};
    pid_t database = start_child(database_executable, database_arguments, database_log);
    if (database < 0) return 1;
    pid_t gateway = -1;
    if (!stopping) gateway = start_child(gateway_executable, gateway_arguments, gateway_log);
    int failed = gateway < 0;
    sigset_t blocked, previous;
    sigemptyset(&previous);
    sigemptyset(&blocked);
    sigaddset(&blocked, SIGTERM);
    sigaddset(&blocked, SIGINT);
    sigaddset(&blocked, SIGCHLD);
    if (sigprocmask(SIG_BLOCK, &blocked, &previous)) failed = 1;
    while (!stopping && !failed) {
        if (reaped(database) || reaped(gateway)) {
            failed = 1;
            fputs("A gateway component exited; restarting the service after cleanup.\n", stderr);
            break;
        }
        // Sleep until termination or child exit, without an idle polling timer.
        sigsuspend(&previous);
    }
    sigprocmask(SIG_SETMASK, &previous, NULL);
    // Release DB connections before asking PostgreSQL to stop.
    stop_child(gateway, 0);
    stop_child(database, 1);
    return stopping ? 0 : 1;
}
