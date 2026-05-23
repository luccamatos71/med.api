from arq.connections import RedisSettings
from app.core.config import settings
from app.workers.material_worker import process_material

REDIS_SETTINGS = RedisSettings.from_dsn(settings.REDIS_URL)


class WorkerSettings:
    redis_settings = REDIS_SETTINGS
    job_timeout = 90
    max_tries = 3
    functions = [process_material]
