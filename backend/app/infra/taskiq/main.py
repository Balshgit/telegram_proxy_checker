from app.infra.taskiq.taskiq_app import create_taskiq_application

app = create_taskiq_application()
scheduler = app.scheduler
broker = app.broker
