// This is the only passwordless privileged entry point. It accepts four fixed
// actions, never a path, command, environment override, or launchd job name.
#include <errno.h>
#include <fcntl.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <sys/wait.h>
#include <unistd.h>

static const char *gateway = "system/local.litellm.gateway";
extern char **environ;
static int run(const char *action, const char *domain, const char *path) {
    pid_t pid = fork();
    if (pid == 0) {
        int fd = open("/dev/null", O_RDWR);
        if (fd < 0 || dup2(fd, 0) < 0 || dup2(fd, 1) < 0 || dup2(fd, 2) < 0) _exit(127);
        if (fd > 2) close(fd);
        if (path) execl("/bin/launchctl", "launchctl", action, domain, path, (char *)NULL);
        else execl("/bin/launchctl", "launchctl", action, domain, (char *)NULL);
        _exit(127);
    }
    if (pid < 0) return -1;
    int status;
    while (waitpid(pid, &status, 0) < 0) if (errno != EINTR) return -1;
    return WIFEXITED(status) ? WEXITSTATUS(status) : -1;
}
static int loaded(const char *job) { return run("print", job, NULL) == 0; }
static int stop(void) {
    if (run("disable", gateway, NULL)) return 1;
    if (loaded(gateway) && run("bootout", gateway, NULL)) return 1;
        // Wait for shutdown before stopping the database; a simple bootout
        // request alone does not establish process termination ordering.
        for (int attempt=0; loaded(gateway); ++attempt) {
            if (attempt >= 320) return 1;
            usleep(250000);
        }
    return 0;
}
static int start(void) {
    if (run("enable", gateway, NULL)) return 1;
    if (!loaded(gateway) && run("bootstrap", "system", "/Library/LaunchDaemons/local.litellm.gateway.plist")) return 1;
    return 0;
}
int main(int argc, char **argv) {
    if (argc != 2 || (strcmp(argv[1], "start") && strcmp(argv[1], "stop") && strcmp(argv[1], "restart") && strcmp(argv[1], "status"))) {
        fputs("Usage: llm-gateway start|stop|restart|status\n", stderr); return 2;
    }
    if (geteuid() != 0) { fputs("Use the llm-gateway command.\n", stderr); return 2; }
    char *clean_env[] = {"PATH=/usr/bin:/bin", "LANG=en_US.UTF-8", NULL};
    environ = clean_env;
    if (chdir("/") < 0) return 1;
    umask(077);
    int lock = open("/Library/Application Support/LiteLLM/control.lock", O_CREAT|O_RDWR|O_NOFOLLOW, 0600);
    struct stat st;
    if (lock < 0 || fstat(lock, &st) || st.st_uid != 0 || !S_ISREG(st.st_mode) || flock(lock, LOCK_EX)) return 1;
    if (!strcmp(argv[1], "status")) {
        printf("LiteLLM Gateway: %s\nDatabase: managed by the same service\nLog rotation: startup and hourly inside gateway\nBackups: manual only\n", loaded(gateway)?"loaded":"stopped");
        return 0;
    }
    int result = 0;
    if (!strcmp(argv[1], "stop") || !strcmp(argv[1], "restart")) result = stop();
    if (!result && (!strcmp(argv[1], "start") || !strcmp(argv[1], "restart"))) result = start();
    if (result) fputs("Service control failed; ask an administrator to inspect the protected logs.\n", stderr);
    else puts(!strcmp(argv[1], "stop") ? "Gateway stopped (also stays stopped after reboot)." : "Gateway services started; allow a moment for database readiness.");
    return result;
}
