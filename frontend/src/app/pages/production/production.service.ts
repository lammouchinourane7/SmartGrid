import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import {
  Dependances, Filtres, ListResponse, MutationResponse, NlpReponse, Options, Source, SourceForm, Stats,
} from './production.models';

/** Appels REST vers backend/modules/production (Flask + RDFLib). */
@Injectable({ providedIn: 'root' })
export class ProductionService {
  private http = inject(HttpClient);
  private base = '/api/production';

  stats() { return this.http.get<Stats>(`${this.base}/stats`); }
  options() { return this.http.get<Options>(`${this.base}/options`); }

  sources(f: Filtres = {}) {
    let params = new HttpParams();
    for (const [k, v] of Object.entries(f)) {
      if (v != null && v !== '' && v !== false) params = params.set(k, String(v));
    }
    return this.http.get<ListResponse<Source>>(`${this.base}/sources`, { params });
  }

  source(id: string) { return this.http.get<{ item: Source; sparql: string }>(`${this.base}/sources/${id}`); }
  dependances(id: string) { return this.http.get<Dependances>(`${this.base}/sources/${id}/dependances`); }
  creer(d: SourceForm) { return this.http.post<MutationResponse>(`${this.base}/sources`, d); }
  modifier(id: string, d: SourceForm) { return this.http.put<MutationResponse>(`${this.base}/sources/${id}`, d); }
  supprimer(id: string) { return this.http.delete<MutationResponse>(`${this.base}/sources/${id}`); }

  question(question: string) { return this.http.post<NlpReponse>(`${this.base}/nlp`, { question }); }
  exemples() { return this.http.get<string[]>(`${this.base}/nlp/exemples`); }
}
