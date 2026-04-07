#!/bin/bash

cd src

if [[ "${1}" == "beat" ]]; then
  celery -A celery_app beat --loglevel=info
elif [[ "${1}" == "worker" ]]; then
  celery -A celery_app worker --loglevel=info
elif [[ "${1}" == "flower" ]]; then
  celery -A celery_app flower --port=5555
fi