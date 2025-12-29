"""Database module - handles MongoDB operations"""
from .mongodb_client import db, MeetingDatabase

__all__ = ['db', 'MeetingDatabase']