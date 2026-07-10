import datetime


def timestamp() -> str:
    t = datetime.datetime.now()
    return t.isoformat()


def log(msg: str) -> None:
    print(f"[{timestamp()}] {msg}", end="\n")
