from sqlalchemy import BigInteger
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class StreamOfferPreference(Base):
    __tablename__ = "stream_offer_preferences"

    stream_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    offer_id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    pinned: Mapped[bool] = mapped_column(default=False)
