import { HttpClient, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import {
  Anomalie, Bilan, Compteur, CompteurForm, Impact, ListResponse, Mesure, MesureFiltres, MesureForm,
  MutationResponse, NlpReponse, Operateur, OperateurForm, Options, Politique, Stats,
} from './mesure.models';

/** Appels REST vers backend/modules/mesure (Flask + RDFLib). */
@Injectable({ providedIn: 'root' })
export class MesureService {
  private http = inject(HttpClient);
  private base = '/api/mesure';

  stats() { return this.http.get<Stats>(`${this.base}/stats`); }
  options() { return this.http.get<Options>(`${this.base}/options`); }
  coherence() { return this.http.get<{ anomalies: Anomalie[]; sparql: string }>(`${this.base}/coherence`); }

  bilan(debut = '', fin = '') {
    let params = new HttpParams();
    if (debut) params = params.set('debut', debut);
    if (fin) params = params.set('fin', fin);
    return this.http.get<Bilan>(`${this.base}/bilan`, { params });
  }

  // compteurs
  compteurs(q = '', batiment = '') {
    let params = new HttpParams();
    if (q) params = params.set('q', q);
    if (batiment) params = params.set('batiment', batiment);
    return this.http.get<ListResponse<Compteur>>(`${this.base}/compteurs`, { params });
  }
  compteur(id: string) { return this.http.get<{ item: Compteur; sparql: string }>(`${this.base}/compteurs/${id}`); }
  impact(id: string, batiment: string) {
    return this.http.get<Impact>(`${this.base}/compteurs/${id}/impact`, { params: { batiment } });
  }
  creerCompteur(d: CompteurForm) { return this.http.post<MutationResponse>(`${this.base}/compteurs`, d); }
  modifierCompteur(id: string, d: CompteurForm, politique?: Politique) {
    return this.http.put<MutationResponse>(`${this.base}/compteurs/${id}`, d, { params: politique ? { politique } : {} });
  }
  supprimerCompteur(id: string, force = false) {
    return this.http.delete<MutationResponse>(`${this.base}/compteurs/${id}`, { params: force ? { force: 'true' } : {} });
  }

  // mesures
  mesures(f: MesureFiltres = {}) {
    let params = new HttpParams();
    for (const [k, v] of Object.entries(f)) {
      if (v != null && v !== '') params = params.set(k, String(v));
    }
    return this.http.get<ListResponse<Mesure> & { mode: string }>(`${this.base}/mesures`, { params });
  }
  mesure(id: string) { return this.http.get<{ item: Mesure; sparql: string }>(`${this.base}/mesures/${id}`); }
  creerMesure(d: MesureForm) { return this.http.post<MutationResponse>(`${this.base}/mesures`, d); }
  modifierMesure(id: string, d: MesureForm) { return this.http.put<MutationResponse>(`${this.base}/mesures/${id}`, d); }
  supprimerMesure(id: string) { return this.http.delete<MutationResponse>(`${this.base}/mesures/${id}`); }

  // opérateurs
  operateurs(q = '') {
    return this.http.get<ListResponse<Operateur>>(`${this.base}/operateurs`, { params: q ? { q } : {} });
  }
  creerOperateur(d: OperateurForm) { return this.http.post<MutationResponse>(`${this.base}/operateurs`, d); }
  modifierOperateur(id: string, d: OperateurForm) { return this.http.put<MutationResponse>(`${this.base}/operateurs/${id}`, d); }
  supprimerOperateur(id: string, force = false) {
    return this.http.delete<MutationResponse>(`${this.base}/operateurs/${id}`, { params: force ? { force: 'true' } : {} });
  }

  question(question: string) { return this.http.post<NlpReponse>(`${this.base}/nlp`, { question }); }
  exemples() { return this.http.get<string[]>(`${this.base}/nlp/exemples`); }
}
