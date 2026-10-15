import csv
import json
import re
import secrets
import shutil
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, BinaryIO


TEXT_FILES_FOLDER = Path(__file__).resolve().parent / "reports" / "text"
TEXT_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}\.txt$")
CSV_FILES_FOLDER = Path(__file__).resolve().parent / "reports" / "csv"
CSV_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}\.csv$")
CSV_EMPLOYEE_FIELDS = ("name", "email", "department", "salary")
JSON_FILES_FOLDER = Path(__file__).resolve().parent / "reports" / "json"
JSON_FILENAME_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,99}\.json$")
UPLOADS_FOLDER = Path(__file__).resolve().parent / "uploads"
ALLOWED_UPLOAD_EXTENSIONS = {".txt", ".csv", ".json"}
MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024
UPLOAD_CHUNK_SIZE_BYTES = 64 * 1024


def get_text_file_path(filename: str) -> Path:
    if not TEXT_FILENAME_PATTERN.fullmatch(filename):
        raise ValueError(
            "Use a .txt filename with letters, numbers, underscores, or hyphens."
        )

    TEXT_FILES_FOLDER.mkdir(parents=True, exist_ok=True)
    folder_path = TEXT_FILES_FOLDER.resolve()
    if folder_path != TEXT_FILES_FOLDER:
        raise ValueError("The text files folder must not be a symbolic link.")

    file_path = folder_path / filename
    if file_path.resolve().parent != folder_path:
        raise ValueError("The file must stay inside the text files folder.")
    return file_path


def create_text_file(filename: str) -> None:
    file_path = get_text_file_path(filename)
    with file_path.open("x", encoding="utf-8"):
        pass


def write_text_file(filename: str, content: str) -> None:
    file_path = get_text_file_path(filename)
    with file_path.open("w", encoding="utf-8") as text_file:
        text_file.write(content)


def append_text_file(filename: str, content: str) -> None:
    file_path = get_text_file_path(filename)
    with file_path.open("a", encoding="utf-8") as text_file:
        text_file.write(content)


def read_text_file(filename: str) -> str:
    file_path = get_text_file_path(filename)
    with file_path.open("r", encoding="utf-8") as text_file:
        return text_file.read()


def read_text_file_lines(filename: str) -> list[str]:
    file_path = get_text_file_path(filename)
    with file_path.open("r", encoding="utf-8") as text_file:
        return [line.rstrip("\r\n") for line in text_file.readlines()]


def text_file_exists(filename: str) -> bool:
    file_path = get_text_file_path(filename)
    return file_path.is_file()


def rename_text_file(filename: str, new_filename: str) -> None:
    file_path = get_text_file_path(filename)
    new_file_path = get_text_file_path(new_filename)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    if new_file_path.exists():
        raise FileExistsError(new_file_path)
    file_path.rename(new_file_path)


def copy_text_file(filename: str, new_filename: str) -> None:
    file_path = get_text_file_path(filename)
    new_file_path = get_text_file_path(new_filename)
    if not file_path.is_file():
        raise FileNotFoundError(file_path)
    if new_file_path.exists():
        raise FileExistsError(new_file_path)
    shutil.copyfile(file_path, new_file_path)


def delete_text_file(filename: str) -> None:
    file_path = get_text_file_path(filename)
    file_path.unlink()


def get_text_file_size(filename: str) -> int:
    file_path = get_text_file_path(filename)
    return file_path.stat().st_size


def get_csv_file_path(filename: str) -> Path:
    if not CSV_FILENAME_PATTERN.fullmatch(filename):
        raise ValueError(
            "Use a .csv filename with letters, numbers, underscores, or hyphens."
        )

    CSV_FILES_FOLDER.mkdir(parents=True, exist_ok=True)
    folder_path = CSV_FILES_FOLDER.resolve()
    if folder_path != CSV_FILES_FOLDER:
        raise ValueError("The CSV files folder must not be a symbolic link.")

    file_path = folder_path / filename
    if file_path.resolve().parent != folder_path:
        raise ValueError("The file must stay inside the CSV files folder.")
    return file_path


def validate_csv_employee_row(
    row: dict[str, str | None], row_number: int
) -> tuple[dict[str, Any] | None, list[str]]:
    errors = []
    employee: dict[str, Any] = {}

    for field in ("name", "email", "department"):
        value = row.get(field)
        if value is None or not value.strip():
            errors.append(f"{field} must not be empty.")
        else:
            employee[field] = value.strip()

    if "email" in employee and "@" not in employee["email"]:
        errors.append("email must contain an @ symbol.")

    salary_value = row.get("salary")
    try:
        salary = Decimal(salary_value.strip()) if salary_value is not None else None
    except InvalidOperation:
        salary = None
    if salary is None or not salary.is_finite() or salary < 0:
        errors.append("salary must be a finite, non-negative number.")
    elif salary > Decimal("99999999.99") or salary.as_tuple().exponent < -2:
        errors.append(
            "salary must fit DECIMAL(10, 2): at most 8 digits before "
            "and 2 digits after the decimal point."
        )
    else:
        employee["salary"] = salary

    if errors:
        return None, [f"Row {row_number}: {error}" for error in errors]
    return employee, []


def read_employee_csv(filename: str) -> dict[str, Any]:
    file_path = get_csv_file_path(filename)
    valid_rows = []
    invalid_rows = []
    seen_emails = set()

    try:
        with file_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file, strict=True)
            if reader.fieldnames is None:
                raise ValueError("The CSV file is empty or has no header row.")

            headers = [header.strip() for header in reader.fieldnames]
            if len(headers) != len(set(headers)) or set(headers) != set(
                CSV_EMPLOYEE_FIELDS
            ):
                required = ", ".join(CSV_EMPLOYEE_FIELDS)
                raise ValueError(f"CSV header must contain exactly: {required}.")

            for row_number, row in enumerate(reader, start=2):
                if None in row:
                    invalid_rows.append(
                        {
                            "row": row_number,
                            "errors": ["Row has more values than the header."],
                        }
                    )
                    continue

                normalized_row = {
                    header.strip(): value for header, value in row.items()
                }
                employee, errors = validate_csv_employee_row(
                    normalized_row, row_number
                )
                if errors:
                    invalid_rows.append({"row": row_number, "errors": errors})
                elif employee is not None:
                    email_key = employee["email"].casefold()
                    if email_key in seen_emails:
                        invalid_rows.append(
                            {
                                "row": row_number,
                                "errors": ["Email is duplicated in this CSV file."],
                            }
                        )
                    else:
                        seen_emails.add(email_key)
                        valid_rows.append(employee)
    except csv.Error as error:
        raise ValueError(f"CSV content is invalid: {error}") from error
    except UnicodeDecodeError as error:
        raise ValueError("CSV file must be UTF-8 encoded.") from error

    if not valid_rows and not invalid_rows:
        raise ValueError("The CSV file contains no employee records.")

    return {"valid_rows": valid_rows, "invalid_rows": invalid_rows}


def write_employee_csv(employees: list[dict[str, Any]], filename: str) -> Path:
    file_path = get_csv_file_path(filename)
    with file_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=("id", *CSV_EMPLOYEE_FIELDS))
        writer.writeheader()
        writer.writerows(employees)
    return file_path


def get_json_file_path(filename: str) -> Path:
    if not JSON_FILENAME_PATTERN.fullmatch(filename):
        raise ValueError(
            "Use a .json filename with letters, numbers, underscores, or hyphens."
        )

    JSON_FILES_FOLDER.mkdir(parents=True, exist_ok=True)
    folder_path = JSON_FILES_FOLDER.resolve()
    if folder_path != JSON_FILES_FOLDER:
        raise ValueError("The JSON files folder must not be a symbolic link.")

    file_path = folder_path / filename
    if file_path.resolve().parent != folder_path:
        raise ValueError("The file must stay inside the JSON files folder.")
    return file_path


def read_json_file(filename: str) -> Any:
    file_path = get_json_file_path(filename)
    try:
        with file_path.open("r", encoding="utf-8") as json_file:
            return json.load(json_file)
    except json.JSONDecodeError as error:
        raise ValueError(
            f"Invalid JSON content on line {error.lineno}, column {error.colno}."
        ) from error
    except UnicodeDecodeError as error:
        raise ValueError("JSON file must be UTF-8 encoded.") from error


def write_json_file(filename: str, data: Any) -> Path:
    file_path = get_json_file_path(filename)
    with file_path.open("w", encoding="utf-8") as json_file:
        json.dump(data, json_file, ensure_ascii=False, indent=2)
        json_file.write("\n")
    return file_path


def write_employee_json(employees: list[dict[str, Any]], filename: str) -> Path:
    json_employees = []
    for employee in employees:
        json_employee = dict(employee)
        salary = json_employee.get("salary")
        if isinstance(salary, Decimal):
            json_employee["salary"] = format(salary, "f")
        json_employees.append(json_employee)
    return write_json_file(filename, json_employees)


def get_uploads_folder() -> Path:
    UPLOADS_FOLDER.mkdir(parents=True, exist_ok=True)
    folder_path = UPLOADS_FOLDER.resolve()
    if folder_path != UPLOADS_FOLDER:
            raise ValueError("The uploads folder must not be a symbolic link.")
    return folder_path


def validate_upload_filename(filename: str) -> str:
    extension = Path(filename).suffix.lower()
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
            allowed_extensions = ", ".join(sorted(ALLOWED_UPLOAD_EXTENSIONS))
            raise ValueError(f"Allowed upload extensions are: {allowed_extensions}.")
    return extension


def create_upload_path(extension: str) -> tuple[str, Path]:
    if extension not in ALLOWED_UPLOAD_EXTENSIONS:
            raise ValueError("Unsupported upload extension.")

    folder_path = get_uploads_folder()
    for _ in range(5):
            stored_filename = f"{secrets.token_hex(16)}{extension}"
            file_path = folder_path / stored_filename
            try:
                with file_path.open("xb"):
                    pass
            except FileExistsError:
                continue
            return stored_filename, file_path
    raise FileExistsError("Could not generate a unique upload filename.")


def save_uploaded_file(uploaded_file: BinaryIO, original_filename: str) -> tuple[str, int]:
    extension = validate_upload_filename(original_filename)
    stored_filename, file_path = create_upload_path(extension)
    total_size = 0
    try:
        with file_path.open("wb") as destination:
            while chunk := uploaded_file.read(UPLOAD_CHUNK_SIZE_BYTES):
                total_size += len(chunk)
                if total_size > MAX_UPLOAD_SIZE_BYTES:
                    raise OverflowError("File exceeds the 5 MB upload limit.")
                destination.write(chunk)
    except Exception:
        file_path.unlink(missing_ok=True)
        raise
    return stored_filename, total_size


def get_upload_path(filename: str) -> Path:
    if not re.fullmatch(r"[a-f0-9]{32}\.(txt|csv|json)", filename):
            raise ValueError("Invalid stored upload filename.")

    folder_path = get_uploads_folder()
    file_path = folder_path / filename
    if file_path.resolve().parent != folder_path:
            raise ValueError("The file must stay inside the uploads folder.")
    if not file_path.is_file():
            raise FileNotFoundError(file_path)
    return file_path
