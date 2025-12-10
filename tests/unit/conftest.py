"""Conftest for unit tests that don't require database fixtures.

This overrides the root conftest.py database setup for standalone unit tests.
"""
import os

# Prevent the root conftest from setting up SQLAlchemy
# by setting environment variables that skip database initialization
os.environ["SKIP_DB_INIT"] = "1"
os.environ["DATABASE_URL"] = "sqlite:///:memory:"
os.environ["ENVIRONMENT"] = "test"
