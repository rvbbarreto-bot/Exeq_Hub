from rest_framework.routers import DefaultRouter

from apps.das.views import GuiaFiscalViewSet

router = DefaultRouter()
router.register("das/guias", GuiaFiscalViewSet, basename="das-guias")

urlpatterns = router.urls
