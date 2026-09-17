// nmail_stub.m — Nmail.app 的「应用面」进程（通用二进制 arm64+x86_64）。
//
// 为什么需要它：LaunchServices 不为纯脚本/无 GUI 的 bundle 注册应用——可执行
// 是 bash 脚本时进程无法成为 Dock 应用，图标点开即消失（2026-09-15 用户实测）。
// 本存根以 NSApplication 身份注册（Dock 图标 = Contents/Resources/AppIcon.icns、
// 名称 = CFBundleName），服务作为它的子进程跑在 Contents/MacOS/server 脚本里；
// 服务运行中再点 Dock 图标走 applicationShouldHandleReopen 重开页面（见 openPage）；
// Dock 右键 Quit / ⌘Q 经 applicationWillTerminate 向子进程发 SIGTERM，由
// server 脚本内的 trap 连带结束 Python。服务子进程退出时应用随退（已在运行的
// 探测场景：cli 开完浏览器即返回，图标自动消失，不留僵尸）。
//
// 编译（通用二进制，见 scripts/ 注释同步 desktop.py）：
//   cc -arch arm64 -arch x86_64 -framework AppKit -framework Foundation -O2 \
//     -o backend/app/assets/nmail-stub scripts/nmail_stub.m
#import <AppKit/AppKit.h>
#import <spawn.h>
#import <sys/wait.h>
#import <libgen.h>
#import <signal.h>
#import <errno.h>
#import <string.h>
#import <unistd.h>
#import <limits.h>
#import <stdlib.h>
#import <stdio.h>

extern char **environ;

static pid_t g_child = -1;
// server 脚本导出 NMAIL_URL_FILE 指向本文件，cli 启动后把实际绑定地址写进来
// （端口可能顺延，8720 被占即漂移）——reopen 据此重开页面
static char g_url_file[PATH_MAX];

static void terminateChild(void) {
    if (g_child <= 0) return;
    kill(g_child, SIGTERM);
    for (int i = 0; i < 30; i++) {           // 最多 3s，不退则升级 SIGKILL
        if (kill(g_child, 0) != 0) { g_child = -1; return; }
        usleep(100000);
    }
    kill(g_child, SIGKILL);
    g_child = -1;
}

// 运行中再点 Dock 图标 → macOS 发 reopen 事件（不会二次启动进程）——用默认
// 浏览器重开页面。URL 文件缺失/没写上时兜底 8720（本应用冷启动的常态端口）
static void openPage(void) {
    const char *url = "http://127.0.0.1:8720";
    char buf[256];
    FILE *fp = fopen(g_url_file, "r");
    if (fp && fgets(buf, sizeof(buf), fp)) {
        buf[strcspn(buf, "\r\n")] = 0;
        if (strncmp(buf, "http://", 7) == 0) url = buf;
    }
    if (fp) fclose(fp);
    pid_t pid;
    char *cargv[] = {(char *)"/usr/bin/open", (char *)url, NULL};
    if (posix_spawn(&pid, "/usr/bin/open", NULL, NULL, cargv, environ) == 0) {
        waitpid(pid, NULL, 0);               // open 秒回，收尸防僵尸
    }
}

@interface NmailDelegate : NSObject <NSApplicationDelegate>
@end
@implementation NmailDelegate
- (void)applicationWillTerminate:(NSNotification *)note { terminateChild(); }
- (BOOL)applicationShouldHandleReopen:(NSApplication *)sender hasVisibleWindows:(BOOL)flag {
    openPage();
    return YES;
}
@end

int main(int argc, const char *argv[]) {
    @autoreleasepool {
        char *self_copy = strdup(argv[0]);
        char *dir = dirname(self_copy);
        char serverPath[PATH_MAX];
        snprintf(serverPath, sizeof(serverPath), "%s/server", dir);
        snprintf(g_url_file, sizeof(g_url_file), "%s/url", dir);

        posix_spawn_file_actions_t fa;
        posix_spawn_file_actions_init(&fa);
        posix_spawn_file_actions_addopen(&fa, STDOUT_FILENO, "/dev/null", O_WRONLY, 0);
        posix_spawn_file_actions_addopen(&fa, STDERR_FILENO, "/dev/null", O_WRONLY, 0);
        char *cargv[] = {(char *)"/bin/bash", serverPath, NULL};
        int rc = posix_spawn(&g_child, "/bin/bash", &fa, NULL, cargv, environ);
        posix_spawn_file_actions_destroy(&fa);
        free(self_copy);
        if (rc != 0) {
            fprintf(stderr, "nmail-stub: spawn server failed: %s\n", strerror(rc));
            return 1;
        }

        NSApplication *app = [NSApplication sharedApplication];
        NmailDelegate *del = [[NmailDelegate alloc] init];
        app.delegate = del;

        // 最小应用菜单：让 ⌘Q 可用（Dock 右键 Quit 不依赖菜单）
        NSMenu *main = [[NSMenu alloc] init];
        NSMenuItem *appItem = [[NSMenuItem alloc] init];
        [main addItem:appItem];
        NSMenu *appMenu = [[NSMenu alloc] init];
        [appMenu addItem:[[NSMenuItem alloc] initWithTitle:@"退出 Nmail"
            action:@selector(terminate:) keyEquivalent:@"q"]];
        [appItem setSubmenu:appMenu];
        app.mainMenu = main;

        // 服务子进程退出 → 应用随退（避免「已在运行」场景留下无服务的图标）
        dispatch_async(dispatch_get_global_queue(QOS_CLASS_BACKGROUND, 0), ^{
            int st;
            waitpid(g_child, &st, 0);
            dispatch_async(dispatch_get_main_queue(), ^{ [NSApp terminate:nil]; });
        });

        [app run];
        terminateChild();
    }
    return 0;
}
