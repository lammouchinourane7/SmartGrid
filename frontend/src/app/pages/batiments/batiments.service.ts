import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import {
  Batiment, BatimentForm, Diagnostic, DiagnosticApplique, Filtres, Inference, ListResponse,
  MutationResponse, NlpReponse, Options, Stats, Triplet,
} from './batiments.models';

/** Appels REST vers backend/modules/batiments (Flask + RDFLib). */
@Injectable({ providedIn: 'root' })
export class BatimentsService {
  private http = inject(HttpClient);
  private base = '/api/batiments';

  stats() { return this.http.get<Stats>(`${this.base}/stats`); }
  options() { return this.http.get<Options>(`${this.base}/options`); }

  batiments(f: Filtres = {}) {
    let params = new HttpParams();
    for (const [k, v] of Object.entries(f)) {
      if (v !== '' && v != null) params = params.set(k, String(v));
    }
    return this.http.get<ListResponse<Batiment>>(`${this.base}/batiments`, { params });
  }

  batiment(id: string) {
    return this.http.get<{ item: Batiment; triplets: Triplet[]; sparql: string }>(`${this.base}/batiments/${id}`);
  }

  creer(d: BatimentForm) { return this.http.post<MutationResponse>(`${this.base}/batiments`, d); }
  modifier(id: string, d: BatimentForm) { return this.http.put<MutationResponse>(`${this.base}/batiments/${id}`, d); }
  changerConsommation(id: string, consommation: number) {
    return this.http.patch<MutationResponse & { consommation: number; gros: boolean }>(
      `${this.base}/batiments/${id}/consommation`, { consommation });
  }
  supprimer(id: string, force = false) {
    return this.http.delete<MutationResponse>(`${this.base}/batiments/${id}`, { params: force ? { force: 'true' } : {} });
  }

  inferences() {
    return this.http.get<{ items: Inference[]; sparql: string; relationsSparql: string }>(`${this.base}/inferences`);
  }

  diagnostic() { return this.http.get<Diagnostic>(`${this.base}/diagnostic`); }
  appliquerDiagnostic(ids: string[] | null) {
    return this.http.post<DiagnosticApplique>(`${this.base}/diagnostic/appliquer`, ids ? { ids } : {});
  }

  question(question: string) { return this.http.post<NlpReponse>(`${this.base}/nlp`, { question }); }
  exemples() { return this.http.get<string[]>(`${this.base}/nlp/exemples`); }
}
