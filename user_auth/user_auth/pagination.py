from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from urllib.parse import urlencode

class PreserveQueryParamsPagination(PageNumberPagination):
    page_size = 5

    def paginate_queryset(self, queryset, request, view=None):
        self.request = request  # IMPORTANT: set self.request here
        return super().paginate_queryset(queryset, request, view)

    def get_paginated_response(self, data):
        request = self.request
        query_params = request.query_params.copy()
        query_params.pop(self.page_query_param, None)

        return Response({
            # 'count': self.page.paginator.count,
            # 'next': self._build_url(request, query_params, self.page.next_page_number()) if self.page.has_next() else None,
            # 'previous': self._build_url(request, query_params, self.page.previous_page_number()) if self.page.has_previous() else None,
            'results': data
        })

    def _build_url(self, request, query_params, page_number):
        query_params[self.page_query_param] = page_number
        return f"{request.path}?{urlencode(query_params)}"
