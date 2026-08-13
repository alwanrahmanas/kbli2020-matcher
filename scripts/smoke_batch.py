"""Exercise the batch upload, streaming, and one-time download workflow."""

import json
from io import BytesIO

import openpyxl
import requests


def make_workbook() -> bytes:
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    sheet.append(["kode"])
    sheet.append(["56101 dan 99999"])
    sheet.append(["56102"])
    output = BytesIO()
    workbook.save(output)
    return output.getvalue()


def main():
    base_url = "http://127.0.0.1:8000"
    payload = make_workbook()
    files = {
        "file": (
            "../contoh<script>.xlsx",
            payload,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    }

    preview = requests.post(f"{base_url}/upload-preview", files=files, timeout=10)
    preview.raise_for_status()
    assert preview.json()["headers"] == ["kode"]
    assert preview.json()["total_rows"] == 2

    response = requests.post(
        f"{base_url}/lookup/batch-stream",
        files=files,
        data={"column_name": "kode"},
        timeout=20,
    )
    response.raise_for_status()
    events = [
        json.loads(line.removeprefix("data: "))
        for line in response.text.splitlines()
        if line.startswith("data: ")
    ]
    complete = next(event for event in events if event["type"] == "complete")
    assert complete["found"] == 2
    assert complete["not_found"] == 0
    assert ".." not in complete["download_url"]
    assert "<" not in complete["download_url"]

    download = requests.get(base_url + complete["download_url"], timeout=10)
    download.raise_for_status()
    result_workbook = openpyxl.load_workbook(BytesIO(download.content))
    result_sheet = result_workbook.active
    assert result_sheet["B2"].value == "[56101] AKTIVITAS PENYEDIAAN MAKANAN DI BANGUNAN TETAP; [99999] Not Found"
    assert result_sheet["C2"].value.startswith("[56101] I AKTIVITAS")
    assert result_sheet["C2"].value.endswith("; [99999] -")
    assert result_sheet["D2"].value == "Found (1/2)"

    second_download = requests.get(base_url + complete["download_url"], timeout=10)
    assert second_download.status_code == 404
    print("batch workflow: OK")


if __name__ == "__main__":
    main()
