from passlib.context import CryptContext

# Configure the password hashing context
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash(password: str) -> str:
    """Generate a bcrypt hash of the password."""
    return pwd_context.hash(password)


def verify(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain password against its hashed version."""
    return pwd_context.verify(plain_password, hashed_password)
