/*
 * Feed REAL ANALOG stick values into chiaki-ng from outside the process.
 *
 * WHY THIS EXISTS
 * ---------------
 * chiaki-ng's keyboard mapping sends fixed, full-deflection stick values; there
 * is no analog channel for a key. A recorded human walk holds the stick at
 * ~0.54, and pulsing a key does not reproduce that — each pulse re-accelerates
 * from a standstill, and it measurably under-travels.
 *
 * chiaki reads its controller through SDL's EVENT QUEUE. A library loaded into
 * chiaki's own process can push SDL_CONTROLLERAXISMOTION events carrying any
 * value in -32768..32767, so 0.54 becomes the literal number 17694 — what a
 * real stick at 0.54 sends. There is no approximation left.
 *
 * Nothing here modifies chiaki, touches SIP, or installs a driver. chiaki is
 * adhoc-signed with no hardened runtime, so DYLD_INSERT_LIBRARIES is permitted,
 * and only a launch that sets that variable is affected.
 *
 * Commands, one per line, on a FIFO:
 *      axis <index> <value>       value -32768..32767
 *      button <index> <0|1>
 *
 * The SDL structs are declared here rather than included, so this builds with
 * no SDL development install. The layouts are SDL2's stable public ABI.
 */
#include <dlfcn.h>
#include <fcntl.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <unistd.h>

#define SDL_CONTROLLERAXISMOTION 0x650
#define SDL_CONTROLLERBUTTONDOWN 0x651
#define SDL_CONTROLLERBUTTONUP   0x652
#define FIFO_PATH "/tmp/chiaki_inject"

typedef int32_t SDL_JoystickID;

typedef struct {
    uint32_t type;
    uint32_t timestamp;
    SDL_JoystickID which;
    uint8_t axis, p1, p2, p3;
    int16_t value;
    uint16_t p4;
} AxisEvent;

typedef struct {
    uint32_t type;
    uint32_t timestamp;
    SDL_JoystickID which;
    uint8_t button, state, p1, p2;
} ButtonEvent;

typedef union {
    uint32_t type;
    AxisEvent caxis;
    ButtonEvent cbutton;
    uint8_t padding[56];
} SDL_Event;

extern void *SDL_GameControllerOpen(int index);

static SDL_JoystickID g_which = -1;   /* instance id chiaki actually opened */

/*
 * Interpose SDL_GameControllerOpen to learn which device chiaki uses.
 * Guessing the instance id would send events to a controller nothing reads,
 * which looks identical to the injection silently not working.
 */
static void *(*real_open)(int) = NULL;

void *my_SDL_GameControllerOpen(int index)
{
    if (!real_open)
        real_open = dlsym(RTLD_NEXT, "SDL_GameControllerOpen");
    void *c = real_open ? real_open(index) : NULL;
    if (c) {
        void *(*getjoy)(void *) = dlsym(RTLD_DEFAULT, "SDL_GameControllerGetJoystick");
        SDL_JoystickID (*instid)(void *) = dlsym(RTLD_DEFAULT, "SDL_JoystickInstanceID");
        if (getjoy && instid) {
            void *j = getjoy(c);
            if (j)
                g_which = instid(j);
        }
        fprintf(stderr, "[inject] controller opened, instance id %d\n", g_which);
    }
    return c;
}

__attribute__((used)) static struct {
    const void *replacement;
    const void *original;
} _interpose_open __attribute__((section("__DATA,__interpose"))) = {
    (const void *)(uintptr_t)&my_SDL_GameControllerOpen,
    (const void *)(uintptr_t)&SDL_GameControllerOpen_stub
};

/* forward declaration so the interpose entry can reference the real symbol */
extern void *SDL_GameControllerOpen(int index);

static int (*p_push)(SDL_Event *) = NULL;

static void push_axis(int axis, int value)
{
    if (!p_push)
        p_push = dlsym(RTLD_DEFAULT, "SDL_PushEvent");
    if (!p_push || g_which < 0)
        return;
    SDL_Event e;
    memset(&e, 0, sizeof e);
    e.caxis.type = SDL_CONTROLLERAXISMOTION;
    e.caxis.which = g_which;
    e.caxis.axis = (uint8_t)axis;
    e.caxis.value = (int16_t)value;
    p_push(&e);
}

static void push_button(int button, int down)
{
    if (!p_push)
        p_push = dlsym(RTLD_DEFAULT, "SDL_PushEvent");
    if (!p_push || g_which < 0)
        return;
    SDL_Event e;
    memset(&e, 0, sizeof e);
    e.cbutton.type = down ? SDL_CONTROLLERBUTTONDOWN : SDL_CONTROLLERBUTTONUP;
    e.cbutton.which = g_which;
    e.cbutton.button = (uint8_t)button;
    e.cbutton.state = down ? 1 : 0;
    p_push(&e);
}

static void *reader(void *unused)
{
    (void)unused;
    unlink(FIFO_PATH);
    if (mkfifo(FIFO_PATH, 0666) != 0) {
        perror("[inject] mkfifo");
        return NULL;
    }
    fprintf(stderr, "[inject] listening on %s\n", FIFO_PATH);
    for (;;) {
        FILE *f = fopen(FIFO_PATH, "r");
        if (!f) {
            sleep(1);
            continue;
        }
        char line[128];
        while (fgets(line, sizeof line, f)) {
            char what[16];
            int a, v;
            if (sscanf(line, "%15s %d %d", what, &a, &v) == 3) {
                if (!strcmp(what, "axis"))
                    push_axis(a, v);
                else if (!strcmp(what, "button"))
                    push_button(a, v);
            }
        }
        fclose(f);
    }
    return NULL;
}

__attribute__((constructor)) static void init(void)
{
    fprintf(stderr, "[inject] loaded into pid %d\n", (int)getpid());
    pthread_t t;
    pthread_create(&t, NULL, reader, NULL);
}
