from rest_framework.filters import SearchFilter


class ColumnSearchFilter(SearchFilter):
    """SearchFilter that searches a page's configured, searchable columns when the view has a table config."""

    def get_search_fields(self, view, request):
        getter = getattr(view, "column_search_fields", None)
        if getter is not None:
            fields = getter()
            if fields is not None:
                return fields
        return super().get_search_fields(view, request)
