import logging, sys, os
from pathlib import Path
from app.models import User, Source
from app.db_connector import get_engine
from sqlalchemy import (
    select,
    delete,
    and_,
    or_,
    text,
    exc,
)
from sqlalchemy.orm import Session

logging.basicConfig(
    stream=sys.stdout,
    format="%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s",
    level=logging.INFO,
    datefmt="%Y-%m-%d %H:%M:%S",
)

engine = get_engine()

class UserHandler:
    def __init__(self):
        self.user = None

    def add_user(self, user: User) -> None:
        """
        This function adds a user to the handler
        """
        if not isinstance(user, User):
            raise TypeError("User must be an instance of User")
        
        if not user.id:
            raise ValueError("User must have a username")
        
        with Session(engine) as session:
            user_exists = session.query(User).filter(User.id == user.id).first()
            if user_exists:
                logging.info(f"User {user.id} already exists")
            else:
                session.add(user)
                session.commit()

    def add_users_from_source(self) -> None:

        ## Get all user_id from Source that are not in User table
        with Session(engine) as session:
            query = select(Source.user_id).where(
                Source.user_id.notin_(select(User.id))
            )
            user_ids = session.execute(query).unique().scalars().all()

            for user_id in user_ids:
                session.add(User(id=user_id))
            session.commit()

    def user_exits(self, user_id: str) -> bool:
        with Session(engine) as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user:
                return True
            return False

    

