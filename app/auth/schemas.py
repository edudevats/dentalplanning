from marshmallow import Schema, fields, validate


class RegisterSchema(Schema):
    tenant_name = fields.Str(required=True, validate=validate.Length(min=2, max=200))
    tenant_slug = fields.Str(required=True, validate=validate.Length(min=2, max=100))
    email = fields.Email(required=True)
    password = fields.Str(required=True, validate=validate.Length(min=6))
    name = fields.Str(required=True, validate=validate.Length(min=2, max=200))


class LoginSchema(Schema):
    email = fields.Email(required=True)
    password = fields.Str(required=True)


class InviteSchema(Schema):
    email = fields.Email(required=True)
    name = fields.Str(required=True)
    role = fields.Str(validate=validate.OneOf(["admin", "editor", "viewer"]), load_default="editor")
    password = fields.Str(required=True, validate=validate.Length(min=6))


class ChangePasswordSchema(Schema):
    current_password = fields.Str(required=True)
    new_password = fields.Str(required=True, validate=validate.Length(min=6))
