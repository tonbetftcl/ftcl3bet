import os
from PIL import Image, ImageDraw, ImageFont, ImageFilter

def create_card_background(width: int = 1200, height: int = 675) -> Image.Image:
    """Создает темный киберспортивный фон с неон-градиентом и размытыми сферами."""
    img = Image.new("RGBA", (width, height), (10, 13, 20, 255))
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Неоновые градиентные пятна (фиолетово-голубая эстетика FTCL)
    draw.ellipse((-100, -100, 500, 500), fill=(88, 101, 242, 70))
    draw.ellipse((width - 400, height - 400, width + 100, height + 100), fill=(236, 72, 153, 60))
    draw.ellipse((width // 2 - 200, height // 2 - 200, width // 2 + 200, height // 2 + 200), fill=(16, 185, 129, 30))

    overlay = overlay.filter(ImageFilter.GaussianBlur(80))
    img = Image.alpha_composite(img, overlay)

    # Рисуем стильную сетку на фоне
    grid_draw = ImageDraw.Draw(img)
    for x in range(0, width, 50):
        grid_draw.line([(x, 0), (x, height)], fill=(255, 255, 255, 8))
    for y in range(0, height, 50):
        grid_draw.line([(0, y), (width, y)], fill=(255, 255, 255, 8))

    return img

def load_font(size: int, bold: bool = False):
    """Загрузка шрифта с фоллбэком на стандартный."""
    font_names = ["arialbd.ttf", "arial.ttf", "DejaVuSans-Bold.ttf", "DejaVuSans.ttf"] if bold else ["arial.ttf", "DejaVuSans.ttf"]
    for font_name in font_names:
        try:
            return ImageFont.truetype(font_name, size)
        except OSError:
            continue
    return ImageFont.load_default()

def generate_bet_banner(
    username: str,
    home_team: str,
    away_team: str,
    outcome: str,
    kef: float,
    amount: float,
    output_path: str = "bet_banner.png"
):
    """Генерирует карточку крупной ставки."""
    img = create_card_background()
    draw = ImageDraw.Draw(img)

    # Полупрозрачная подложка-карточка
    card_box = [60, 60, 1140, 615]
    draw.rounded_rectangle(card_box, radius=24, fill=(20, 26, 38, 200), outline=(255, 255, 255, 30), width=2)

    font_title = load_font(42, bold=True)
    font_match = load_font(54, bold=True)
    font_sub = load_font(32, bold=False)
    font_kef = load_font(60, bold=True)

    # Заголовок
    draw.text((100, 100), "🔥 КРУПНАЯ СТАВКА FTCL³", font=font_title, fill=(245, 158, 11))
    draw.text((100, 160), f"Игрок: {username}", font=font_sub, fill=(156, 163, 175))

    # Матч
    match_str = f"{home_team}  VS  {away_team}"
    draw.text((100, 250), match_str, font=font_match, fill=(255, 255, 255))

    # Информация о ставке (Плашки)
    draw.rounded_rectangle([100, 360, 420, 470], radius=16, fill=(30, 41, 59, 255), outline=(59, 130, 246, 100), width=2)
    draw.text((120, 375), "Исходи:", font=font_sub, fill=(148, 163, 184))
    draw.text((120, 415), str(outcome), font=font_kef, fill=(59, 130, 246))

    draw.rounded_rectangle([450, 360, 770, 470], radius=16, fill=(30, 41, 59, 255), outline=(16, 185, 129, 100), width=2)
    draw.text((470, 375), "Коэффициент:", font=font_sub, fill=(148, 163, 184))
    draw.text((470, 415), f"x{kef:.2f}", font=font_kef, fill=(16, 185, 129))

    draw.rounded_rectangle([800, 360, 1100, 470], radius=16, fill=(30, 41, 59, 255), outline=(236, 72, 153, 100), width=2)
    draw.text((820, 375), "Сумма:", font=font_sub, fill=(148, 163, 184))
    draw.text((820, 415), f"{amount:,.0f}", font=font_kef, fill=(236, 72, 153))

    # Возможный выигрыш
    possible_win = amount * kef
    draw.text((100, 520), f"🚀 Возможный выигрыш: {possible_win:,.0f} монет", font=font_title, fill=(34, 197, 94))

    img.save(output_path)
    return output_path
