#!/bin/bash

# Function to start the uvicorn server
start_server() {
    echo "[$(date)] Starting uvicorn server..."
    uvicorn app:app --host 0.0.0.0 --port 8080 --env-file .env --reload &
    SERVER_PID=$!
    echo "[$(date)] Server started with PID: $SERVER_PID"
}

# Function to stop the server
stop_server() {
    if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
        echo "[$(date)] Stopping server (PID: $SERVER_PID)..."
        kill "$SERVER_PID"
        wait "$SERVER_PID" 2>/dev/null
        echo "[$(date)] Server stopped."
    fi
}

# Handle script termination
cleanup() {
    echo "[$(date)] Received shutdown signal..."
    stop_server
    exit 0
}

trap cleanup SIGINT SIGTERM

# Main loop
while true; do
    start_server

    # Wait until midnight
    while true; do
        # Check if server is still running
        if ! kill -0 "$SERVER_PID" 2>/dev/null; then
            echo "[$(date)] Server crashed, restarting..."
            break
        fi

        # Check if it's midnight (00:00)
        CURRENT_HOUR=$(date +%H)
        CURRENT_MIN=$(date +%M)

        if [ "$CURRENT_HOUR" = "00" ] && [ "$CURRENT_MIN" = "00" ]; then
            echo "[$(date)] Midnight reached, restarting server..."
            stop_server
            sleep 61  # Sleep past the minute to avoid multiple restarts
            break
        fi

        sleep 30  # Check every 30 seconds
    done
done