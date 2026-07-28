from app.bot import build_dig_rich_message


def test_dig_rich_message_keeps_details_collapsed() -> None:
    message = build_dig_rich_message(
        player_name="@miner [Хозяин глубин]",
        summary="Камень остановил раскопку. Удалось пройти 1 м.",
        dug=1,
        coins=27,
        total_depth=1106,
        luck_text="95 → 60",
        route_name="Глубинная зона",
        level=50,
        xp=14580,
        streak=21,
        expedition_progress=33,
        expedition_target=50,
        details=[
            "Артефакт: снова найден «Старая монета». Дубликат продан за <b>2</b> котоинов.",
            "Сработали эффекты: кирка +6%; вагонетка +35%",
        ],
    )

    dumped = message.model_dump(mode="json", exclude_none=True)
    blocks = dumped["blocks"]

    assert blocks[0]["type"] == "paragraph"
    assert blocks[1]["type"] == "paragraph"
    assert blocks[2]["type"] == "table"
    assert blocks[2]["cells"][0][0]["text"] == "Глубина"
    assert blocks[2]["cells"][1][1]["text"] == "+27"
    assert blocks[3] == {
        "type": "details",
        "summary": "Подробнее ниже",
        "blocks": [
            {"type": "paragraph", "text": "Маршрут: Глубинная зона."},
            {"type": "paragraph", "text": "Уровень 50, XP 14580, серия 21."},
            {"type": "paragraph", "text": "Экспедиция группы: 33/50 м."},
            {"type": "paragraph", "text": "Артефакт: снова найден «Старая монета»."},
            {"type": "paragraph", "text": "Дубликат продан за 2 котоинов."},
            {"type": "paragraph", "text": "Сработали эффекты:"},
            {"type": "paragraph", "text": "кирка +6%"},
            {"type": "paragraph", "text": "вагонетка +35%"},
        ],
        "is_open": False,
    }
