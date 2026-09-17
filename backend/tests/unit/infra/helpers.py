from datetime import timedelta

SCHEDULED_TASK_NAME = "test_interval_task"
CONTROL_TASK_NAME = "test_control_interval_task"

# Секунда — минимум, ниже которого taskiq не работает, а не осторожно выбранное значение:
# `is_interval_task_now` сравнивает `round(seconds_passed) >= round(interval_seconds)`,
# а `SchedulerLoop.run` выравнивает тики по секундам (`next_run.replace(microsecond=0)`)
# и при более коротком `loop_interval` уходит в busy loop с отрицательной задержкой.
TASK_INTERVAL = timedelta(seconds=1)
CRON_TASK_INTERVAL = timedelta(hours=1)

# Крон ночной очистки протухших проксей: каждый день в 3 часа ночи.
# Значение прибито гвоздями намеренно: тест должен падать, если расписание переедет на другое время.
CLEANUP_TASK_CRON = "0 2 * * *"

# Крон добора новых проксей: каждые 6 часов, в начале часа.
# Значение прибито гвоздями намеренно: тест должен падать, если расписание переедет на другое время.
ADD_PROXIES_TASK_CRON = "0 */6 * * *"

# Лейблы кроновой задачи добора проксей. Она единственная ретраится: источники живут на github,
# и разовая сетевая ошибка не должна означать, что новых проксей не будет ещё 6 часов.
ADD_PROXIES_TASK_LABELS = {"timeout": 30, "retry_on_error": True, "max_retries": 2}

# Интервал заведомо больше, чем тест успеет прождать: любое выполнение такой таски —
# это тот самый незапрошенный первый запуск на старте приложения, а не срабатывание по расписанию.
UNREACHABLE_TASK_INTERVAL = timedelta(hours=4)

# Боевые интервалы (TASKIQ_SCHEDULES_UPDATE_INTERVAL = 1 час, TASKIQ_SCHEDULER_LOOP_INTERVAL = 5 минут)
# в тестах недостижимы: после первого тика цикл планировщика уходит спать на 5 минут, поэтому
# интервальная таска успевает отработать ровно один раз. На время теста ужимаем интервалы до секунды.
SCHEDULES_UPDATE_INTERVAL_FOR_TESTS = timedelta(seconds=1)
SCHEDULER_LOOP_INTERVAL_FOR_TESTS = timedelta(seconds=1)
