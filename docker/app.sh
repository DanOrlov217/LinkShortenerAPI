#!/bin/bash

echo "Waiting for database..."
until python -c "
import asyncio, asyncpg, os
async def check():
    await asyncpg.connect(
        user=os.getenv('DB_USER'), password=os.getenv('DB_PASS'),
        host=os.getenv('DB_HOST'), port=os.getenv('DB_PORT'),
        database=os.getenv('DB_NAME')
    )
asyncio.run(check())
" 2>/dev/null; do
    echo "Database not ready, retrying in 2s..."
    sleep 2
done
echo "Database is ready."

alembic upgrade head

cd src

gunicorn main:app --workers 4 --worker-class uvicorn.workers.UvicornWorker --bind=0.0.0.0:8000