from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import mysql.connector
from fastapi import Body, FastAPI, File, HTTPException, Query, Response, UploadFile, status
from fastapi.responses import FileResponse, RedirectResponse

import file_operations
import employee_queries


app = FastAPI(title="Employee Management API")


@app.get("/", include_in_schema=False)
def docs_redirect() -> RedirectResponse:
    return RedirectResponse(url=app.docs_url)


def validate_employee_data(data: dict[str, Any]) -> dict[str, Any]:
    required_fields = ("name", "email", "department", "salary")
    missing_fields = [field for field in required_fields if field not in data]
    if missing_fields:
        missing_names = ", ".join(missing_fields)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Missing required fields: {missing_names}",
        )

    employee: dict[str, Any] = {}
    for field in ("name", "email", "department"):
        value = data[field]
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"{field} must be a non-empty string.",
            )
        employee[field] = value.strip()

    if "@" not in employee["email"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="email must contain an @ symbol.",
        )

    salary_value = data["salary"]
    if isinstance(salary_value, bool) or not isinstance(salary_value, (int, float)):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="salary must be a non-negative number.",
        )
    try:
        salary = Decimal(str(salary_value))
    except InvalidOperation as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="salary must be a valid number.",
        ) from error
    if not salary.is_finite() or salary < 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="salary must be a finite, non-negative number.",
        )
    if salary > Decimal("99999999.99") or salary.as_tuple().exponent < -2:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="salary must fit DECIMAL(10, 2): at most 8 digits before "
            "and 2 digits after the decimal point.",
        )
    employee["salary"] = salary
    return employee


def database_http_error(error: Exception) -> HTTPException:
    if isinstance(error, ConnectionError):
        return HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        )
    if isinstance(error, ValueError):
        return HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(error),
        )
    if isinstance(error, mysql.connector.Error) and error.errno == 1062:
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="An employee with that email already exists.",
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="A database error occurred while processing the request.",
    )


def file_http_error(error: OSError | ValueError) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested text file does not exist.",
        )
    if isinstance(error, FileExistsError):
        return HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A text file with that name already exists.",
        )
    if isinstance(error, PermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The application does not have permission to access that file.",
        )
    if isinstance(error, ValueError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="A file operation failed.",
    )


def csv_http_error(error: OSError | ValueError) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested CSV file does not exist.",
        )
    if isinstance(error, PermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The application does not have permission to access that file.",
        )
    if isinstance(error, ValueError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="A CSV file operation failed.",
    )


def json_http_error(error: OSError | ValueError) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested JSON file does not exist.",
        )
    if isinstance(error, PermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The application does not have permission to access that file.",
        )
    if isinstance(error, ValueError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="A JSON file operation failed.",
    )


def upload_http_error(error: OSError | ValueError) -> HTTPException:
    if isinstance(error, FileNotFoundError):
        return HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="The requested uploaded file does not exist.",
        )
    if isinstance(error, PermissionError):
        return HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="The application does not have permission to access that file.",
        )
    if isinstance(error, ValueError):
        return HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        )
    return HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="An upload or download file operation failed.",
    )


@app.post("/files/upload", status_code=status.HTTP_201_CREATED)
def upload_file(file: UploadFile = File(...)) -> dict[str, Any]:
    original_filename = file.filename or ""
    try:
        stored_filename, total_size = file_operations.save_uploaded_file(
            file.file, original_filename
        )
    except OverflowError as error:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=str(error),
        ) from error
    except (OSError, ValueError) as error:
        raise upload_http_error(error) from error
    finally:
        file.file.close()

    return {
        "message": "File uploaded.",
        "filename": stored_filename,
        "original_filename": Path(original_filename).name,
        "size_bytes": total_size,
    }


@app.get("/files/download/{filename}")
def download_file(filename: str) -> FileResponse:
    try:
        file_path = file_operations.get_upload_path(filename)
    except (OSError, ValueError) as error:
        raise upload_http_error(error) from error
    return FileResponse(
        path=file_path,
        media_type="application/octet-stream",
        filename=filename,
    )


@app.post("/employees", status_code=status.HTTP_201_CREATED)
def create_employee(data: dict[str, Any] = Body(...)) -> dict[str, Any]:
    employee = validate_employee_data(data)
    try:
        employee_id = employee_queries.add_employee(employee)
    except (ConnectionError, ValueError, mysql.connector.Error) as error:
        raise database_http_error(error) from error
    return {"id": employee_id, **employee}


@app.get("/employees")
def list_employees() -> list[dict[str, Any]]:
    try:
        return employee_queries.get_all_employees()
    except (ConnectionError, ValueError, mysql.connector.Error) as error:
        raise database_http_error(error) from error


@app.get("/employees/export-csv")
def export_employees_csv() -> FileResponse:
    try:
        employees = employee_queries.get_all_employees()
    except (ConnectionError, ValueError, mysql.connector.Error) as error:
        raise database_http_error(error) from error

    try:
        file_path = file_operations.write_employee_csv(
            employees, "employee_export.csv"
        )
    except (OSError, ValueError) as error:
        raise csv_http_error(error) from error
    return FileResponse(
        path=file_path,
        media_type="text/csv",
        filename="employee_export.csv",
    )


@app.get("/employees/export-json")
def export_employees_json() -> FileResponse:
    try:
        employees = employee_queries.get_all_employees()
    except (ConnectionError, ValueError, mysql.connector.Error) as error:
        raise database_http_error(error) from error

    try:
        file_path = file_operations.write_employee_json(
            employees, "employee_export.json"
        )
    except (OSError, ValueError) as error:
        raise json_http_error(error) from error
    return FileResponse(
        path=file_path,
        media_type="application/json",
        filename="employee_export.json",
    )


@app.get("/files/json/{filename}")
def read_json_file(filename: str) -> Any:
    try:
        return file_operations.read_json_file(filename)
    except (OSError, ValueError) as error:
        raise json_http_error(error) from error


@app.put("/files/json/{filename}")
def write_json_file(filename: str, data: Any = Body(...)) -> dict[str, str]:
    try:
        file_operations.write_json_file(filename, data)
    except (OSError, ValueError) as error:
        raise json_http_error(error) from error
    return {"message": "JSON file written.", "filename": filename}


@app.get("/employees/import-csv/{filename}/preview")
def preview_employees_csv(filename: str) -> dict[str, Any]:
    try:
        result = file_operations.read_employee_csv(filename)
    except (OSError, ValueError) as error:
        raise csv_http_error(error) from error
    preview_rows = [
        {**employee, "salary": str(employee["salary"])}
        for employee in result["valid_rows"]
    ]
    return {
        "valid_count": len(preview_rows),
        "invalid_count": len(result["invalid_rows"]),
        "valid_rows": preview_rows,
        "invalid_rows": result["invalid_rows"],
    }


@app.post("/employees/import-csv/{filename}")
def import_employees_csv(filename: str) -> dict[str, Any]:
    try:
        result = file_operations.read_employee_csv(filename)
    except (OSError, ValueError) as error:
        raise csv_http_error(error) from error

    if result["invalid_rows"]:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "CSV import rejected; correct all invalid rows and retry.",
                "invalid_rows": result["invalid_rows"],
            },
        )

    try:
        imported_count = employee_queries.add_employees(result["valid_rows"])
    except (ConnectionError, ValueError, mysql.connector.Error) as error:
        raise database_http_error(error) from error
    return {"message": "CSV records imported.", "imported_count": imported_count}


@app.get("/employees/search")
def find_employees(
    name: str | None = Query(default=None),
    department: str | None = Query(default=None),
) -> list[dict[str, Any]]:
    if name is not None:
        name = name.strip()
    if department is not None:
        department = department.strip()
    if not name and not department:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Provide a name, a department, or both to search.",
        )
    try:
        return employee_queries.search_employees(name, department)
    except (ConnectionError, ValueError, mysql.connector.Error) as error:
        raise database_http_error(error) from error


@app.get("/employees/{employee_id}")
def find_employee(employee_id: int) -> dict[str, Any]:
    try:
        employee = employee_queries.get_employee_by_id(employee_id)
    except (ConnectionError, ValueError, mysql.connector.Error) as error:
        raise database_http_error(error) from error
    if employee is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )
    return employee


@app.put("/employees/{employee_id}")
def edit_employee(
    employee_id: int, data: dict[str, Any] = Body(...)
) -> dict[str, Any]:
    employee = validate_employee_data(data)
    try:
        existing_employee = employee_queries.get_employee_by_id(employee_id)
        if existing_employee is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Employee not found.",
            )
        employee_queries.update_employee(employee_id, employee)
    except (ConnectionError, ValueError, mysql.connector.Error) as error:
        raise database_http_error(error) from error
    return {"id": employee_id, **employee}


@app.delete("/employees/{employee_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_employee(employee_id: int) -> Response:
    try:
        deleted_rows = employee_queries.delete_employee(employee_id)
    except (ConnectionError, ValueError, mysql.connector.Error) as error:
        raise database_http_error(error) from error
    if deleted_rows == 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Employee not found.",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/files/text/{filename}", status_code=status.HTTP_201_CREATED)
def create_text_file(filename: str) -> dict[str, str]:
    try:
        file_operations.create_text_file(filename)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return {"message": "Text file created.", "filename": filename}


@app.put("/files/text/{filename}")
def write_text_file(
    filename: str, content: str = Body(..., media_type="text/plain")
) -> dict[str, str]:
    try:
        file_operations.write_text_file(filename, content)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return {"message": "Text file written.", "filename": filename}


@app.post("/files/text/{filename}/append")
def append_text_file(
    filename: str, content: str = Body(..., media_type="text/plain")
) -> dict[str, str]:
    try:
        file_operations.append_text_file(filename, content)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return {"message": "Text appended.", "filename": filename}


@app.get("/files/text/{filename}")
def read_text_file(filename: str) -> dict[str, str]:
    try:
        content = file_operations.read_text_file(filename)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return {"filename": filename, "content": content}


@app.get("/files/text/{filename}/lines")
def read_text_file_lines(filename: str) -> dict[str, Any]:
    try:
        lines = file_operations.read_text_file_lines(filename)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return {"filename": filename, "lines": lines}


@app.get("/files/text/{filename}/exists")
def check_text_file_exists(filename: str) -> dict[str, Any]:
    try:
        exists = file_operations.text_file_exists(filename)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return {"filename": filename, "exists": exists}


@app.post("/files/text/{filename}/rename")
def rename_text_file(
    filename: str, data: dict[str, str] = Body(...)
) -> dict[str, str]:
    new_filename = data.get("new_filename")
    if not new_filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="new_filename is required.",
        )
    try:
        file_operations.rename_text_file(filename, new_filename)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return {"message": "Text file renamed.", "filename": new_filename}


@app.post("/files/text/{filename}/copy", status_code=status.HTTP_201_CREATED)
def copy_text_file(
    filename: str, data: dict[str, str] = Body(...)
) -> dict[str, str]:
    new_filename = data.get("new_filename")
    if not new_filename:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="new_filename is required.",
        )
    try:
        file_operations.copy_text_file(filename, new_filename)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return {"message": "Text file copied.", "filename": new_filename}


@app.delete("/files/text/{filename}", status_code=status.HTTP_204_NO_CONTENT)
def delete_text_file(filename: str) -> Response:
    try:
        file_operations.delete_text_file(filename)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.get("/files/text/{filename}/size")
def get_text_file_size(filename: str) -> dict[str, Any]:
    try:
        size_bytes = file_operations.get_text_file_size(filename)
    except (OSError, ValueError) as error:
        raise file_http_error(error) from error
    return {"filename": filename, "size_bytes": size_bytes}
