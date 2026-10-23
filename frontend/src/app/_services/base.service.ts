import { HttpClient, HttpHeaders, HttpParams, HttpParameterCodec, HttpResponse } from '@angular/common/http';
import { Observable, throwError } from 'rxjs';
import { catchError } from 'rxjs/operators';
import { environment } from '../../environments/environment';

export class BaseService {
  protected get headers(): HttpHeaders {
    return new HttpHeaders();
  }

  errorKeyMap: Record<string, string> = {};

  protected baseUrl = window.location.origin.includes('localhost') || window.location.origin.includes('127.0.0.1')
    ? 'http://127.0.0.1:8000/api/v1'
    : `${environment.BACKEND_PUBLIC_DOMAIN}/api/v1`;

  constructor(protected http: HttpClient) {}

  protected get(url: string, params?: HttpParams): Observable<unknown> {
    return this.http.get(url, { headers: this.headers, params }).pipe(catchError(this.getErrorHandler()));
  }

  protected getErrorHandler() {
    return (res: { status?: number; error?: unknown; message?: string }) => {
      let errorMessages: string[] = [];
      if (res?.error && typeof res.error === 'object' && !Array.isArray(res.error)) {
        errorMessages = Object.entries(res.error as Record<string, unknown>).map(([key, value]) => {
          const keyName = this.errorKeyMap[key] || key;
          return `${keyName}: ${value}`;
        });
      } else if (typeof res?.error === 'string' && res.error.trim()) {
        errorMessages = [res.error.slice(0, 200)];
      } else {
        errorMessages = [res?.message || 'Request failed'];
      }

      return throwError(
        () =>
          ({
            status: res?.status ?? 0,
            response: res,
            errorMessages,
          }) as HttpErrorResponse,
      );
    };
  }
}

export class HttpErrorResponse {
  status!: number;
  response!: HttpResponse<unknown> | unknown;
  errorMessages!: string[];
}

export class CustomHttpParamEncoder implements HttpParameterCodec {
  encodeKey(key: string): string {
    return encodeURIComponent(key);
  }
  encodeValue(value: string): string {
    return encodeURIComponent(value);
  }
  decodeKey(key: string): string {
    return decodeURIComponent(key);
  }
  decodeValue(value: string): string {
    return decodeURIComponent(value);
  }
}
