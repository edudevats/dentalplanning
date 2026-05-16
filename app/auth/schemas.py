from marshmallow import Schema, fields, validate, validates, ValidationError
import re


def _validate_password_strength(password):
    """Enforce min 8 chars, at least 1 uppercase, 1 lowercase, 1 digit."""
    if len(password) < 8:
        raise ValidationError("La contraseña debe tener al menos 8 caracteres")
    if not re.search(r"[A-Z]", password):
        raise ValidationError("La contraseña debe tener al menos una mayúscula")
    if not re.search(r"[a-z]", password):
        raise ValidationError("La contraseña debe tener al menos una minúscula")
    if not re.search(r"\d", password):
        raise ValidationError("La contraseña debe tener al menos un número")


class RegisterSchema(Schema):
    tenant_name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    tenant_slug = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=8))
    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    contact_email = fields.Email(required=False, load_default=None)
    plan_id = fields.Int(required=True)

    @validates("password")
    def validate_password(self, value, **kwargs):
        _validate_password_strength(value)


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)


class InviteSchema(Schema):
    email = fields.Email(required=True)
    name = fields.Str(required=True)
    role = fields.Str(validate=validate.OneOf(["admin", "editor", "viewer"]), load_default="editor")
    password = fields.Str(required=True, validate=validate.Length(min=8))

    @validates("password")
    def validate_password(self, value, **kwargs):
        _validate_password_strength(value)


class ChangePasswordSchema(Schema):
    current_password = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate.Length(min=8))

    @validates("new_password")
    def validate_password(self, value, **kwargs):
        _validate_password_strength(value)
