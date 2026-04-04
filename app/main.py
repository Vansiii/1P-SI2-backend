from fastapi import FastAPI

app = FastAPI(title="Examen 1P API", version="0.1.0")


@app.get("/")
def read_root() -> dict[str, str]:
    return {"message": "API de FastAPI inicializada correctamente"}


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
