#!/usr/bin/env python3

"""Тесты для plugins/employees/login_generator.py — SAP-стиль генерации
логина по ФИО (транслитерация, фамилия+инициалы, до 12 символов, обработка
коллизий сокращением/цифровым суффиксом)."""

from plugins.employees.login_generator import (
    generate_login_candidates,
    generate_unique_login,
)


class TestGenerateLoginCandidates:
    def test_basic_transliteration(self):
        candidates = generate_login_candidates("Иванов Иван Иванович")
        assert candidates[0] == "ivanovii"

    def test_all_candidates_within_max_length(self):
        candidates = generate_login_candidates(
            "Константинопольский Константин Константинович", max_length=12
        )
        assert all(len(c) <= 12 for c in candidates)

    def test_single_word_name_still_produces_candidate(self):
        candidates = generate_login_candidates("Мадонна")
        assert candidates
        assert candidates[0] == "madonna"

    def test_empty_name_falls_back_to_user(self):
        assert generate_login_candidates("") == ["user"]
        assert generate_login_candidates("   ") == ["user"]

    def test_candidates_are_unique_and_non_empty(self):
        candidates = generate_login_candidates("Петров Пётр Петрович")
        assert len(candidates) == len(set(candidates))
        assert all(c for c in candidates)

    def test_latin_name_passthrough(self):
        candidates = generate_login_candidates("Smith John")
        assert candidates[0].startswith("smith")


class TestGenerateUniqueLogin:
    def test_returns_first_candidate_when_free(self):
        login = generate_unique_login("Иванов Иван Иванович", is_taken=lambda x: False)
        assert login == "ivanovii"

    def test_falls_back_to_shorter_candidate_on_collision(self):
        taken = {"ivanovii"}
        login = generate_unique_login(
            "Иванов Иван Иванович", is_taken=lambda x: x in taken
        )
        assert login != "ivanovii"
        assert login not in taken

    def test_falls_back_to_numeric_suffix_when_all_candidates_taken(self):
        def always_taken(login: str) -> bool:
            return not login.endswith(("7", "8", "9"))

        login = generate_unique_login("Иванов Иван Иванович", is_taken=always_taken)
        assert login[-1] in ("7", "8", "9")

    def test_deterministic_for_same_input(self):
        first = generate_unique_login("Сидоров Сидор Сидорович", is_taken=lambda x: False)
        second = generate_unique_login("Сидоров Сидор Сидорович", is_taken=lambda x: False)
        assert first == second
