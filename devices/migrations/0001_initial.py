import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Device",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, verbose_name="Название")),
                ("host", models.CharField(max_length=255, verbose_name="IP / хост")),
                ("port", models.PositiveIntegerField(default=502, verbose_name="Порт")),
                ("unit_id", models.PositiveSmallIntegerField(default=1, verbose_name="Modbus ID")),
                ("enabled", models.BooleanField(default=True, verbose_name="Опрос включён")),
                ("poll_interval", models.FloatField(default=5.0, verbose_name="Период опроса, с")),
                ("timeout", models.FloatField(default=3.0, verbose_name="Таймаут, с")),
                ("retries", models.PositiveSmallIntegerField(default=1, verbose_name="Повторы")),
                ("online", models.BooleanField(default=False, verbose_name="В сети")),
                ("last_attempt", models.DateTimeField(blank=True, null=True, verbose_name="Последняя попытка")),
                ("last_success", models.DateTimeField(blank=True, null=True, verbose_name="Последний успех")),
                ("last_error", models.TextField(blank=True, default="", verbose_name="Последняя ошибка")),
                ("latency_ms", models.FloatField(default=0.0, verbose_name="Задержка, мс")),
                ("latest_values", models.JSONField(blank=True, default=dict, verbose_name="Последние значения")),
                ("channel_availability", models.JSONField(blank=True, default=dict, verbose_name="Доступность каналов")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
            ],
            options={
                "verbose_name": "Устройство",
                "verbose_name_plural": "Устройства",
                "ordering": ["name", "id"],
            },
        ),
        migrations.CreateModel(
            name="Channel",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=150, verbose_name="Имя канала")),
                ("address", models.PositiveIntegerField(default=0, verbose_name="Адрес регистра")),
                (
                    "function",
                    models.CharField(
                        choices=[
                            ("holding", "Holding (03)"),
                            ("input", "Input (04)"),
                            ("coil", "Coil (01)"),
                            ("discrete", "Discrete (02)"),
                        ],
                        default="holding",
                        max_length=20,
                        verbose_name="Функция",
                    ),
                ),
                (
                    "data_type",
                    models.CharField(
                        choices=[
                            ("int16", "int16"),
                            ("uint16", "uint16"),
                            ("int32", "int32"),
                            ("uint32", "uint32"),
                            ("float32", "float32"),
                        ],
                        default="uint16",
                        max_length=20,
                        verbose_name="Тип данных",
                    ),
                ),
                ("scale", models.FloatField(default=1.0, verbose_name="Масштаб")),
                ("unit", models.CharField(blank=True, default="", max_length=32, verbose_name="Единица")),
                (
                    "word_order",
                    models.CharField(
                        choices=[
                            ("big", "Старшее слово первым (ABCD)"),
                            ("little", "Младшее слово первым (CDAB)"),
                        ],
                        default="big",
                        max_length=10,
                        verbose_name="Порядок слов",
                    ),
                ),
                ("writable", models.BooleanField(default=False, verbose_name="Запись")),
                ("order", models.PositiveIntegerField(default=0, verbose_name="Порядок")),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="channels",
                        to="devices.device",
                        verbose_name="Устройство",
                    ),
                ),
            ],
            options={
                "verbose_name": "Канал",
                "verbose_name_plural": "Каналы",
                "ordering": ["order", "id"],
            },
        ),
        migrations.CreateModel(
            name="Measurement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("channel", models.CharField(db_index=True, max_length=150, verbose_name="Канал")),
                ("value", models.FloatField(blank=True, null=True, verbose_name="Значение")),
                ("measured_at", models.DateTimeField(db_index=True, verbose_name="Время измерения")),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="measurements",
                        to="devices.device",
                        verbose_name="Устройство",
                    ),
                ),
            ],
            options={
                "verbose_name": "Измерение",
                "verbose_name_plural": "Измерения",
                "ordering": ["measured_at"],
            },
        ),
        migrations.AddConstraint(
            model_name="channel",
            constraint=models.UniqueConstraint(
                fields=("device", "name"), name="unique_channel_name_per_device"
            ),
        ),
        migrations.AddIndex(
            model_name="measurement",
            index=models.Index(fields=["device", "measured_at"], name="measure_device_time_idx"),
        ),
        migrations.AddIndex(
            model_name="measurement",
            index=models.Index(
                fields=["device", "channel", "measured_at"], name="measure_chan_time_idx"
            ),
        ),
    ]
