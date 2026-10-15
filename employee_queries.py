from typing import Any

from database import get_db_connection


def _run_write_query(query: str, values: tuple[Any, ...]) -> tuple[int, int]:
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.execute(query, values)
            connection.commit()
            return cursor.lastrowid, cursor.rowcount
        finally:
            cursor.close()
    finally:
        connection.close()


def _run_select_query(
    query: str, values: tuple[Any, ...] = ()
) -> list[dict[str, Any]]:
    connection = get_db_connection()
    try:
        cursor = connection.cursor(dictionary=True)
        try:
            cursor.execute(query, values)
            return cursor.fetchall()
        finally:
            cursor.close()
    finally:
        connection.close()


def add_employee(employee: dict[str, Any]) -> int:
    query = """
        INSERT INTO employees (name, email, department, salary)
        VALUES (%s, %s, %s, %s)
    """
    employee_id, _ = _run_write_query(
        query,
        (
            employee["name"],
            employee["email"],
            employee["department"],
            employee["salary"],
        ),
    )
    return employee_id


def add_employees(employees: list[dict[str, Any]]) -> int:
    query = """
        INSERT INTO employees (name, email, department, salary)
        VALUES (%s, %s, %s, %s)
    """
    connection = get_db_connection()
    try:
        cursor = connection.cursor()
        try:
            cursor.executemany(
                query,
                [
                    (
                        employee["name"],
                        employee["email"],
                        employee["department"],
                        employee["salary"],
                    )
                    for employee in employees
                ],
            )
            connection.commit()
            return cursor.rowcount
        except Exception:
            connection.rollback()
            raise
        finally:
            cursor.close()
    finally:
        connection.close()


def get_all_employees() -> list[dict[str, Any]]:
    query = """
        SELECT id, name, email, department, salary
        FROM employees
        ORDER BY id
    """
    return _run_select_query(query)


def get_employee_by_id(employee_id: int) -> dict[str, Any] | None:
    query = """
        SELECT id, name, email, department, salary
        FROM employees
        WHERE id = %s
    """
    employees = _run_select_query(query, (employee_id,))
    if not employees:
        return None
    return employees[0]


def update_employee(employee_id: int, employee: dict[str, Any]) -> int:
    query = """
        UPDATE employees
        SET name = %s, email = %s, department = %s, salary = %s
        WHERE id = %s
    """
    _, affected_rows = _run_write_query(
        query,
        (
            employee["name"],
            employee["email"],
            employee["department"],
            employee["salary"],
            employee_id,
        ),
    )
    return affected_rows


def delete_employee(employee_id: int) -> int:
    query = "DELETE FROM employees WHERE id = %s"
    _, affected_rows = _run_write_query(query, (employee_id,))
    return affected_rows


def search_employees(
    name: str | None, department: str | None
) -> list[dict[str, Any]]:
    conditions = []
    values: list[Any] = []

    if name:
        conditions.append("name LIKE %s")
        values.append(f"%{name}%")
    if department:
        conditions.append("department LIKE %s")
        values.append(f"%{department}%")
    if not conditions:
        raise ValueError("Provide a name, a department, or both to search.")

    query = """
        SELECT id, name, email, department, salary
        FROM employees
        WHERE """ + " AND ".join(conditions) + """
        ORDER BY id
    """
    return _run_select_query(query, tuple(values))
