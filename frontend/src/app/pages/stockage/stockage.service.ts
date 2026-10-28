import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import {
  BatimentStockage, Filtres, ListResponse, MutationResponse, NlpReponse, Options,
  Scenario, ScenarioApplique, Stats, Systeme, SystemeForm, Triplet,
} from './stockage.models';

/** Appels REST vers backend/modules/stockage (Flask + RDFLib). */
@Injectable({ providedIn: 'root' })
export class StockageService {
  private http = inject(HttpClient);
  private base = '/api/stockage';

  stats() { return this.http.get<Stats>(`${this.base}/stats`); }
  options() { return this.http.get<Options>(`${this.base}/options`); }

  systemes(f: Filtres = {}) {
    let params = new HttpParams();
    for (const [k, v] of Object.entries(f)) {
      if (v !== '' && v != null) params = params.set(k, String(v));
    }
    return this.http.get<ListResponse<Systeme>>(`${this.base}/systemes`, { params });
  }

  systeme(id: string) {
    return this.http.get<{ item: Systeme; triplets: Triplet[]; sparql: string }>(`${this.base}/systemes/${id}`);
  }

  creer(d: SystemeForm) { return this.http.post<MutationResponse>(`${this.base}/systemes`, d); }
  modifier(id: string, d: SystemeForm) { return this.http.put<MutationResponse>(`${this.base}/systemes/${id}`, d); }
  changerNiveau(id: string, niveau: number) {
    return this.http.patch<MutationResponse & { niveau: number }>(`${this.base}/systemes/${id}/niveau`, { niveau });
  }
  supprimer(id: string, force = false) {
    return this.http.delete<MutationResponse>(`${this.base}/systemes/${id}`, { params: force ? { force: 'true' } : {} });
  }

  batiments() { return this.http.get<ListResponse<BatimentStockage>>(`${this.base}/batiments`); }

  scenario(poste: string, heures: number) {
    const params: Record<string, string> = { heures: String(heures) };
    if (poste) params['poste'] = poste;
    return this.http.get<Scenario>(`${this.base}/scenario`, { params });
  }
  appliquerScenario(poste: string, heures: number) {
    return this.http.post<ScenarioApplique>(`${this.base}/scenario/appliquer`, { poste: poste || null, heures });
  }

  question(question: string) { return this.http.post<NlpReponse>(`${this.base}/nlp`, { question }); }
  exemples() { return this.http.get<string[]>(`${this.base}/nlp/exemples`); }
}
