from datetime import timedelta

SCHEDULED_TASK_NAME = "test_interval_task"
TASK_INTERVAL = timedelta(seconds=1)
CRON_TASK_INTERVAL = timedelta(hours=4)

# Боевые интервалы (TASKIQ_SCHEDULES_UPDATE_INTERVAL = 1 час, TASKIQ_SCHEDULER_LOOP_INTERVAL = 5 минут)
# в тестах недостижимы: после первого тика цикл планировщика уходит спать на 5 минут, поэтому
# интервальная таска успевает отработать ровно один раз. На время теста ужимаем интервалы до секунды.
SCHEDULES_UPDATE_INTERVAL_FOR_TESTS = timedelta(seconds=1)
SCHEDULER_LOOP_INTERVAL_FOR_TESTS = timedelta(seconds=1)
