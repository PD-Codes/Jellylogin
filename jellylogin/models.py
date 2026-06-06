from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=True)
    role = db.Column(db.String(20), nullable=False, default="user")
    auth_type = db.Column(db.String(20), nullable=False, default="local")
    jellyfin_user_id = db.Column(db.String(64), nullable=True, unique=True)
    is_active = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    last_login = db.Column(db.DateTime, nullable=True)

    def to_dict(self):
        return {
            "id": self.id,
            "username": self.username,
            "role": self.role,
            "auth_type": self.auth_type,
            "is_active": self.is_active,
            "created_at": self.created_at.isoformat(),
            "last_login": self.last_login.isoformat() if self.last_login else None,
        }


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    icon = db.Column(db.String(64), nullable=True)
    order = db.Column(db.Integer, nullable=False, default=0)
    links = db.relationship(
        "LinkCard",
        backref="category",
        lazy=True,
        foreign_keys="LinkCard.category_id",
        order_by="LinkCard.order",
    )

    def to_dict(self):
        return {"id": self.id, "name": self.name, "icon": self.icon, "order": self.order}


class LinkCard(db.Model):
    __tablename__ = "link_cards"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    url = db.Column(db.String(512), nullable=False)
    description = db.Column(db.String(256), nullable=True)
    icon = db.Column(db.String(256), nullable=True)
    bg_color = db.Column(db.String(32), nullable=False, default="#1e1b4b")
    bg_image = db.Column(db.String(512), nullable=True)
    style = db.Column(db.String(20), nullable=False, default="glass")
    open_in_new_tab = db.Column(db.Boolean, nullable=False, default=True)
    category_id = db.Column(
        db.Integer,
        db.ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    order = db.Column(db.Integer, nullable=False, default=0)
    check_status = db.Column(db.Boolean, nullable=False, default=True)
    is_visible = db.Column(db.Boolean, nullable=False, default=True)
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "url": self.url,
            "description": self.description,
            "icon": self.icon,
            "bg_color": self.bg_color,
            "bg_image": self.bg_image,
            "style": self.style,
            "open_in_new_tab": self.open_in_new_tab,
            "category_id": self.category_id,
            "order": self.order,
            "check_status": self.check_status,
            "is_visible": self.is_visible,
        }


class Setting(db.Model):
    __tablename__ = "settings"

    key = db.Column(db.String(64), primary_key=True)
    value = db.Column(db.Text, nullable=True)


class JellyfinConfig(db.Model):
    __tablename__ = "jellyfin_config"

    id = db.Column(db.Integer, primary_key=True)
    server_url = db.Column(db.String(256), nullable=False, default="")
    api_key = db.Column(db.String(256), nullable=False, default="")
    auto_create_users = db.Column(db.Boolean, nullable=False, default=True)
    default_role = db.Column(db.String(20), nullable=False, default="user")
