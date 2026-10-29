FROM node:22-slim AS webbuild
WORKDIR /app/web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
ARG VITE_TOMTOM_API_KEY
ARG VITE_MAX_ROUTES
ARG VITE_DEFAULT_MAX_ROUTES
ARG VITE_SEARCH_DEBOUNCE_MS
ARG VITE_MIN_SEARCH_LENGTH
ENV VITE_TOMTOM_API_KEY=$VITE_TOMTOM_API_KEY \
    VITE_MAX_ROUTES=$VITE_MAX_ROUTES \
    VITE_DEFAULT_MAX_ROUTES=$VITE_DEFAULT_MAX_ROUTES \
    VITE_SEARCH_DEBOUNCE_MS=$VITE_SEARCH_DEBOUNCE_MS \
    VITE_MIN_SEARCH_LENGTH=$VITE_MIN_SEARCH_LENGTH
RUN npm run build

FROM python:3.12-slim AS runtime
WORKDIR /app
COPY pyproject.toml ./
COPY app ./app
RUN pip install --no-cache-dir .
COPY --from=webbuild /app/web/dist ./web/dist
EXPOSE 8000
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
