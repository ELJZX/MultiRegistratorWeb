from django.db import models


class Device(models.Model):
    name = models.CharField("Название", max_length=150)
    host = models.CharField("IP / хост", max_length=255)
    port = models.PositiveIntegerField("Порт", default=502)
    unit_id = models.PositiveSmallIntegerField("Modbus ID", default=1)
    enabled = models.BooleanField("Опрос включён", default=True)
    poll_interval = models.FloatField("Период опроса, с", default=5.0)
    timeout = models.FloatField("Таймаут, с", default=3.0)
    retries = models.PositiveSmallIntegerField("Повторы", default=1)

    online = models.BooleanField("В сети", default=False)
    last_attempt = models.DateTimeField("Последняя попытка", null=True, blank=True)
    last_success = models.DateTimeField("Последний успех", null=True, blank=True)
    last_error = models.TextField("Последняя ошибка", blank=True, default="")
    latency_ms = models.FloatField("Задержка, мс", default=0.0)
    latest_values = models.JSONField("Последние значения", default=dict, blank=True)
    channel_availability = models.JSONField("Доступность каналов", default=dict, blank=True)

    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Устройство"
        verbose_name_plural = "Устройства"
        ordering = ["name", "id"]

    def __str__(self):
        return f"{self.name} ({self.host}:{self.port})"

    @property
    def channel_names(self):
        return [channel.name for channel in self.channels.all()]

    @property
    def is_online(self):
        return bool(self.online)

    @property
    def status_css(self):
        return "online" if self.online else "offline"


class Channel(models.Model):
    class Function(models.TextChoices):
        HOLDING = "holding", "Holding (03)"
        INPUT = "input", "Input (04)"
        COIL = "coil", "Coil (01)"
        DISCRETE = "discrete", "Discrete (02)"

    class DataType(models.TextChoices):
        INT16 = "int16", "int16"
        UINT16 = "uint16", "uint16"
        INT32 = "int32", "int32"
        UINT32 = "uint32", "uint32"
        FLOAT32 = "float32", "float32"

    device = models.ForeignKey(
        Device, related_name="channels", on_delete=models.CASCADE, verbose_name="Устройство"
    )
    name = models.CharField("Имя канала", max_length=150)
    address = models.PositiveIntegerField("Адрес регистра", default=0)
    function = models.CharField(
        "Функция", max_length=20, choices=Function.choices, default=Function.HOLDING
    )
    data_type = models.CharField(
        "Тип данных", max_length=20, choices=DataType.choices, default=DataType.UINT16
    )
    scale = models.FloatField("Масштаб", default=1.0)
    unit = models.CharField("Единица", max_length=32, blank=True, default="")
    word_order = models.CharField(
        "Порядок слов",
        max_length=10,
        choices=[("big", "Старшее слово первым (ABCD)"), ("little", "Младшее слово первым (CDAB)")],
        default="big",
    )
    writable = models.BooleanField("Запись", default=False)
    order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Канал"
        verbose_name_plural = "Каналы"
        ordering = ["order", "id"]
        constraints = [
            models.UniqueConstraint(fields=["device", "name"], name="unique_channel_name_per_device")
        ]

    def __str__(self):
        return f"{self.name} @{self.address}"

    @property
    def is_bit(self):
        return self.function in (self.Function.COIL, self.Function.DISCRETE)

    @property
    def word_count(self):
        if self.data_type in (self.DataType.INT32, self.DataType.UINT32, self.DataType.FLOAT32):
            return 2
        return 1

    def to_dict(self):
        return {
            "name": self.name,
            "address": self.address,
            "function": self.function,
            "data_type": self.data_type,
            "scale": self.scale,
            "unit": self.unit,
            "word_order": self.word_order,
            "writable": self.writable,
        }


class Measurement(models.Model):
    device = models.ForeignKey(
        Device, related_name="measurements", on_delete=models.CASCADE, verbose_name="Устройство"
    )
    channel = models.CharField("Канал", max_length=150, db_index=True)
    value = models.FloatField("Значение", null=True, blank=True)
    measured_at = models.DateTimeField("Время измерения", db_index=True)

    class Meta:
        verbose_name = "Измерение"
        verbose_name_plural = "Измерения"
        ordering = ["measured_at"]
        indexes = [
            models.Index(fields=["device", "measured_at"], name="measure_device_time_idx"),
            models.Index(fields=["device", "channel", "measured_at"], name="measure_chan_time_idx"),
        ]

    def __str__(self):
        return f"{self.device_id} {self.channel}={self.value} @ {self.measured_at}"
