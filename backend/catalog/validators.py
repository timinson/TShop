from django.core.exceptions import ValidationError


def validate_image_size(value):
    if value.size > 5 * 1024 * 1024:
        raise ValidationError('Размер изображения не должен превышать 5 МБ.')
