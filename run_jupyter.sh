

PORT="$1"
echo $PORT

if [ -z "$BUILD_PROD" ]; then
   PORT=8891
fi
export PYTHONPATH="$PYTHONPATH:$(pwd)" && jupyter lab --NotebookApp.iopub_data_rate_limit=1.0e10 --ip=0.0.0.0 --port=$PORT
