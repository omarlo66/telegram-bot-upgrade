from typing import Union

from django.db import models


class GroupFamily(models.Model):
    main_group = models.ForeignKey('common.Group', related_name='group_families', on_delete=models.CASCADE)
    subgroups = models.ManyToManyField('common.Group', blank=True)

    @property
    async def subgroup_titles(self):
        return ', '.join([subgroup.title async for subgroup in self.subgroups.all()])

    @classmethod
    async def aget_by_main_group(cls, group_id) -> Union['GroupFamily', None]:
        return await cls.objects.filter(main_group__telegram_id=group_id).afirst()

    @classmethod
    def from_json(cls, data: dict) -> tuple['GroupFamily', bool]:
        from src.common.models import Group

        subgroups = []

        for subgroup_data in data.pop('subgroups', []):
            subgroups.append(Group.from_json(data=subgroup_data)[0])

        data['main_group'], _ = Group.from_json(data=data['main_group'])
        group_family, created = cls.objects.get_or_create(**data)
        group_family.subgroups.set(subgroups)
        return group_family, created
