#include <time.h>
#include <sched.h>
#include <unistd.h>
#include <errno.h>
#include <stdint.h>
#include <stddef.h>

extern "C" int buzzer_play_edges(int value_fd, const double *edge_seconds, size_t count) {
  int old_policy = sched_getscheduler(0);
  struct sched_param old_param;
  bool restore = old_policy != -1 && sched_getparam(0, &old_param) == 0;
  struct sched_param fifo_param = {};
  fifo_param.sched_priority = 50;
  if (restore) sched_setscheduler(0, SCHED_FIFO, &fifo_param);

  struct timespec start;
  clock_gettime(CLOCK_MONOTONIC, &start);
  int result = 0;
  for (size_t i = 0; i < count; ++i) {
    int64_t deadline_ns = (int64_t)start.tv_sec * 1000000000LL + start.tv_nsec + (int64_t)(edge_seconds[i] * 1000000000.0);
    struct timespec now;
    clock_gettime(CLOCK_MONOTONIC, &now);
    int64_t now_ns = (int64_t)now.tv_sec * 1000000000LL + now.tv_nsec;
    if (deadline_ns - now_ns > 200000) {
      int64_t sleep_ns = deadline_ns - 200000;
      struct timespec sleep_deadline = { (time_t)(sleep_ns / 1000000000LL), (long)(sleep_ns % 1000000000LL) };
      while (clock_nanosleep(CLOCK_MONOTONIC, TIMER_ABSTIME, &sleep_deadline, NULL) == EINTR) {}
    }
    do {
      clock_gettime(CLOCK_MONOTONIC, &now);
      now_ns = (int64_t)now.tv_sec * 1000000000LL + now.tv_nsec;
    } while (now_ns < deadline_ns);
    if (write(value_fd, i % 2 == 0 ? "1" : "0", 1) < 0) {
      result = -errno;
      break;
    }
  }
  write(value_fd, "0", 1);
  if (restore) sched_setscheduler(0, old_policy, &old_param);
  return result;
}
