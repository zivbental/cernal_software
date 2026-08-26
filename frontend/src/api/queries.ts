/**
 * React Query hooks. Components use these, never `api` directly.
 *
 * The one that matters: `useRunStatus` polls while a run is in flight and stops on a
 * terminal status, which is how the product stays honest about long-running work.
 */

import {
  useMutation,
  useQuery,
  useQueryClient,
  type UseQueryOptions,
} from "@tanstack/react-query";

import { api } from "./client";
import {
  isTerminal,
  type Annotation,
  type Artifact,
  type Candidate,
  type CandidateDetail,
  type Dataset,
  type DecisionTag,
  type Paginated,
  type Project,
  type Run,
  type RunParams,
  type RunStatusResponse,
  type User,
  type Version,
} from "./types";

export const keys = {
  me: ["me"] as const,
  version: ["version"] as const,
  projects: ["projects"] as const,
  project: (id: string) => ["project", id] as const,
  datasets: (projectId: string) => ["datasets", projectId] as const,
  runs: (projectId: string) => ["runs", projectId] as const,
  recentRuns: ["runs", "recent"] as const,
  run: (id: string) => ["run", id] as const,
  runStatus: (id: string) => ["run", id, "status"] as const,
  candidates: (runId: string, params: string) => ["candidates", runId, params] as const,
  candidate: (id: string) => ["candidate", id] as const,
  artifacts: (runId: string) => ["artifacts", runId] as const,
  annotations: (candidateId: string) => ["annotations", candidateId] as const,
};

/* ---------- session ---------- */

export function useMe(options?: Partial<UseQueryOptions<User | null>>) {
  return useQuery({
    queryKey: keys.me,
    queryFn: () => api.get<User>("/auth/me").catch(() => null),
    staleTime: 5 * 60_000,
    retry: false,
    ...options,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (credentials: { username: string; password: string }) =>
      api.post<User>("/auth/login", credentials),
    onSuccess: (user) => {
      queryClient.setQueryData(keys.me, user);
    },
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<void>("/auth/logout"),
    onSuccess: () => {
      queryClient.clear();
    },
  });
}

/** Engine capabilities — which mechanisms exist and which are selectable. */
export function useVersion() {
  return useQuery({
    queryKey: keys.version,
    queryFn: () => api.get<Version>("/version"),
    staleTime: Infinity,
  });
}

/* ---------- projects ---------- */

export function useProjects() {
  return useQuery({ queryKey: keys.projects, queryFn: () => api.get<Project[]>("/projects") });
}

export function useProject(id: string) {
  return useQuery({
    queryKey: keys.project(id),
    queryFn: () => api.get<Project>(`/projects/${id}`),
    enabled: Boolean(id),
  });
}

export function useCreateProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { name: string; organism: string; biological_objective?: string }) =>
      api.post<Project>("/projects", body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.projects }),
  });
}

export function useDeleteProject() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/projects/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.projects }),
  });
}

/* ---------- datasets ---------- */

export function useDatasets(projectId: string) {
  return useQuery({
    queryKey: keys.datasets(projectId),
    queryFn: () => api.get<Dataset[]>(`/projects/${projectId}/datasets`),
    enabled: Boolean(projectId),
  });
}

export function useUploadDataset(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return api.upload<Dataset>(`/projects/${projectId}/datasets`, form);
    },
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.datasets(projectId) }),
  });
}

/* ---------- runs ---------- */

export interface SubmitRunBody {
  input_mode: "de" | "direct";
  dataset_id?: string | null;
  trigger_sequence?: string;
  params?: RunParams;
  gate_families?: string[];
  scoring_profile?: string;
  seed?: number | null;
  idempotency_key?: string;
}

export function useSubmitRun(projectId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: SubmitRunBody) => api.post<Run>(`/projects/${projectId}/runs`, body),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: keys.runs(projectId) });
      queryClient.invalidateQueries({ queryKey: keys.recentRuns });
    },
  });
}

export function useRecentRuns(limit = 20) {
  return useQuery({
    queryKey: keys.recentRuns,
    queryFn: () => api.get<Run[]>(`/runs?limit=${limit}`),
  });
}

export function useProjectRuns(projectId: string) {
  return useQuery({
    queryKey: keys.runs(projectId),
    queryFn: () => api.get<Run[]>(`/projects/${projectId}/runs`),
    enabled: Boolean(projectId),
  });
}

export function useRun(id: string) {
  return useQuery({
    queryKey: keys.run(id),
    queryFn: () => api.get<Run>(`/runs/${id}/detail`),
    enabled: Boolean(id),
  });
}

/**
 * Poll a run while it is in flight.
 *
 * Refetching stops the moment the run reaches a terminal status, so a completed run
 * costs nothing to leave open on screen.
 */
export function useRunStatus(id: string, intervalMs = 3000) {
  return useQuery({
    queryKey: keys.runStatus(id),
    queryFn: () => api.get<RunStatusResponse>(`/runs/${id}`),
    enabled: Boolean(id),
    staleTime: 0,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && isTerminal(status) ? false : intervalMs;
    },
  });
}

export function useCancelRun(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => api.post<{ id: string; status: string; outcome: string }>(`/runs/${id}/cancel`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.runStatus(id) }),
  });
}

/* ---------- results ---------- */

export interface CandidateFilters {
  sort?: string;
  gateFamily?: string;
  includeRejected?: boolean;
  limit?: number;
  offset?: number;
}

export function useCandidates(runId: string, filters: CandidateFilters = {}, enabled = true) {
  const search = new URLSearchParams();
  search.set("limit", String(filters.limit ?? 200));
  if (filters.offset) search.set("offset", String(filters.offset));
  if (filters.sort) search.set("sort", filters.sort);
  if (filters.gateFamily) search.set("gate_family", filters.gateFamily);
  if (filters.includeRejected) search.set("include_rejected", "true");
  const query = search.toString();

  return useQuery({
    queryKey: keys.candidates(runId, query),
    queryFn: () => api.get<Paginated<Candidate>>(`/runs/${runId}/candidates?${query}`),
    enabled: enabled && Boolean(runId),
  });
}

export function useCandidate(id: string | null) {
  return useQuery({
    queryKey: keys.candidate(id ?? ""),
    queryFn: () => api.get<CandidateDetail>(`/candidates/${id}`),
    enabled: Boolean(id),
  });
}

export function useArtifacts(runId: string, enabled = true) {
  return useQuery({
    queryKey: keys.artifacts(runId),
    queryFn: () => api.get<Artifact[]>(`/runs/${runId}/artifacts`),
    enabled: enabled && Boolean(runId),
  });
}

/* ---------- annotations ---------- */

export function useAnnotations(candidateId: string | null) {
  return useQuery({
    queryKey: keys.annotations(candidateId ?? ""),
    queryFn: () => api.get<Annotation[]>(`/candidates/${candidateId}/annotations`),
    enabled: Boolean(candidateId),
  });
}

export function useCreateAnnotation(candidateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { text: string; decision_tag: DecisionTag }) =>
      api.post<Annotation>(`/candidates/${candidateId}/annotations`, body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.annotations(candidateId) }),
  });
}

export function useDeleteAnnotation(candidateId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.delete<void>(`/annotations/${id}`),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: keys.annotations(candidateId) }),
  });
}
