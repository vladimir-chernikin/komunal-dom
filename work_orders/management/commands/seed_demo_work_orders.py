from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Команда устарела после удаления типовых маршрутов."

    def handle(self, *args, **options):
        raise CommandError(
            "seed_demo_work_orders отключена: типовые маршруты удалены. "
            "Для заполнения маршрутов услуг компании используйте seed_aspect_service_routes."
        )
