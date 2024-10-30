class HumanEntityMixin:
    first_name: str
    last_name: str

    @property
    def full_name(self) -> str | None:
        if self.first_name:
            if self.last_name:
                return f'{self.first_name} {self.last_name}'
            else:
                return self.first_name

        elif self.last_name:
            return self.last_name
