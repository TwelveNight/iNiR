/* Steam's GTK2 dereferences XRRGetOutputInfo/ XRRGetCrtcInfo without NULL checks.
 * A monitor can disappear between querying resources and querying its details.
 * Only Steam + GTK2 calls get an empty disconnected result in that race.
 * The constructor restores LD_PRELOAD before Steam starts child processes.
 */
#define _GNU_SOURCE
#include <X11/Xlib.h>
#include <X11/extensions/Xrandr.h>
#include <dlfcn.h>
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

__attribute__((constructor)) static void restore_child_environment(void) {
    const char *previous = getenv("INIR_STEAM_PREVIOUS_PRELOAD");
    if (!previous) return;
    if (*previous) setenv("LD_PRELOAD", previous, 1);
    else unsetenv("LD_PRELOAD");
    unsetenv("INIR_STEAM_PREVIOUS_PRELOAD");
    fprintf(stderr, "[inir-steam] GTK2 RandR guard loaded; child preload environment restored\n");
}

static int is_steam_gtk2(void *caller) {
    Dl_info info;
    const char *name = strrchr(program_invocation_name, '/');
    name = name ? name + 1 : program_invocation_name;
    if (strcmp(name, "steam") || !dladdr(caller, &info) || !info.dli_fname)
        return 0;
    const char *library = strrchr(info.dli_fname, '/');
    library = library ? library + 1 : info.dli_fname;
    return strncmp(library, "libgdk-x11-2.0.so", 17) == 0;
}

XRROutputInfo *XRRGetOutputInfo(Display *display, XRRScreenResources *resources,
                              RROutput output) {
    typedef XRROutputInfo *(*query_fn)(Display *, XRRScreenResources *, RROutput);
    query_fn query = (query_fn)dlsym(RTLD_NEXT, "XRRGetOutputInfo");
    XRROutputInfo *result = query ? query(display, resources, output) : NULL;
    if (result || !is_steam_gtk2(__builtin_return_address(0)))
        return result;
    /* XRRFreeOutputInfo uses XFree on the contiguous allocation. */
    result = calloc(1, sizeof(*result) + 1);
    if (!result) abort();
    result->name = (char *)(result + 1);
    result->connection = RR_Disconnected;
    fprintf(stderr, "[inir-steam] GTK2 RandR: vanished output %lu treated as disconnected\n", output);
    return result;
}

XRRCrtcInfo *XRRGetCrtcInfo(Display *display, XRRScreenResources *resources,
                          RRCrtc crtc) {
    typedef XRRCrtcInfo *(*query_fn)(Display *, XRRScreenResources *, RRCrtc);
    query_fn query = (query_fn)dlsym(RTLD_NEXT, "XRRGetCrtcInfo");
    XRRCrtcInfo *result = query ? query(display, resources, crtc) : NULL;
    if (result || !is_steam_gtk2(__builtin_return_address(0)))
        return result;
    result = calloc(1, sizeof(*result));
    if (!result) abort();
    fprintf(stderr, "[inir-steam] GTK2 RandR: vanished CRTC %lu treated as inactive\n", crtc);
    return result;
}
