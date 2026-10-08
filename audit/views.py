from django.views.generic import ListView

from accounts.permissions import AdminRequiredMixin

from .models import AuditLog


class AuditLogListView(AdminRequiredMixin, ListView):
    model = AuditLog
    template_name = "audit/log_list.html"
    paginate_by = 25
    context_object_name = "logs"

    def get_queryset(self):
        qs = AuditLog.objects.select_related("user")
        action = self.request.GET.get("action")
        model_name = self.request.GET.get("model")
        if action in AuditLog.Action.values:
            qs = qs.filter(action=action)
        if model_name:
            qs = qs.filter(model_name=model_name)
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["action_choices"] = AuditLog.Action.choices
        ctx["model_names"] = AuditLog.objects.order_by().values_list("model_name", flat=True).distinct().order_by("model_name")
        ctx["selected_action"] = self.request.GET.get("action", "")
        ctx["selected_model"] = self.request.GET.get("model", "")
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx["query_string"] = params.urlencode()
        return ctx