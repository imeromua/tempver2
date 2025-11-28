#!/usr/bin/env python3
"""Скрипт для форматування та перевірки коду проекту."""

import subprocess
import sys
from pathlib import Path


def run_command(command, description):
    """Виконує команду та виводить результат."""
    print(f"\n{'='*50}")
    print(f"🔧 {description}")
    print(f"{'='*50}")

    try:
        result = subprocess.run(command, capture_output=True, text=True, check=False)

        if result.stdout:
            print(result.stdout)
        if result.stderr:
            print(result.stderr)

        if result.returncode != 0:
            print("⚠️ Помилки знайдено!")
            return False
        else:
            print("✅ Успішно виконано!")
            return True

    except FileNotFoundError:
        print(f"❌ Інструмент не встановлено! Встановіть: pip install {command[0]}")
        return False


def main():
    """Основна функція для запуску всіх інструментів."""
    Path(".")

    print("🚀 Початок форматування та перевірки проекту...")

    # Крок 1: Сортування імпортів через isort
    isort_success = run_command(
        ["isort", ".", "--profile=black", "--line-length=88"],
        "Сортування імпортів (isort)",
    )

    # Крок 2: Форматування коду через Black
    black_success = run_command(
        ["black", ".", "--line-length=88"], "Форматування коду (black)"
    )

    # Крок 3: Перевірка через flake8
    flake8_success = run_command(
        ["flake8", ".", "--max-line-length=88", "--extend-ignore=E203,W503"],
        "Перевірка коду (flake8)",
    )

    # Підсумок
    print(f"\n{'='*50}")
    print("📊 ПІДСУМОК")
    print(f"{'='*50}")
    print(f"isort:  {'✅' if isort_success else '❌'}")
    print(f"black:  {'✅' if black_success else '❌'}")
    print(f"flake8: {'✅' if flake8_success else '❌'}")

    if not all([isort_success, black_success, flake8_success]):
        sys.exit(1)
    else:
        print("\n🎉 Всі перевірки пройдено успішно!")
        sys.exit(0)


if __name__ == "__main__":
    main()
