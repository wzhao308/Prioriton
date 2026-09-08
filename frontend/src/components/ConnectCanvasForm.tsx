import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";

export default function ConnectCanvasForm() {
  const [baseUrl, setBaseUrl] = useState("");
  const [token, setToken] = useState("");
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => api.connectCanvas(baseUrl.trim(), token.trim()),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["integrations"] });
      queryClient.invalidateQueries({ queryKey: ["courses"] });
      queryClient.invalidateQueries({ queryKey: ["tasks"] });
      setToken("");
    },
  });

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
      className="space-y-3"
    >
      <div>
        <label className="block text-sm font-medium text-stone-700">Canvas URL</label>
        <input
          type="url"
          required
          placeholder="https://yourschool.instructure.com"
          value={baseUrl}
          onChange={(e) => setBaseUrl(e.target.value)}
          className="mt-1 w-full rounded-xl border border-stone-300 px-3 py-2 text-sm"
        />
      </div>
      <div>
        <label className="block text-sm font-medium text-stone-700">Personal access token</label>
        <input
          type="password"
          required
          placeholder="paste your Canvas token"
          value={token}
          onChange={(e) => setToken(e.target.value)}
          className="mt-1 w-full rounded-xl border border-stone-300 px-3 py-2 text-sm"
        />
        <p className="mt-1 text-xs text-stone-500">
          Generate one in Canvas under Account → Settings → "+ New Access Token". It's stored
          encrypted on your own machine, never sent anywhere but Canvas.
        </p>
      </div>
      <button
        type="submit"
        disabled={mutation.isPending}
        className="rounded-xl bg-matcha-600 px-4 py-2 text-sm font-medium text-white hover:bg-matcha-700 disabled:opacity-50"
      >
        {mutation.isPending ? "Connecting…" : "Connect Canvas"}
      </button>
      {mutation.isError && (
        <p className="text-sm text-red-600">{(mutation.error as Error).message}</p>
      )}
      {mutation.isSuccess && (
        <p className="text-sm text-emerald-600">Connected! Courses and assignments are synced.</p>
      )}
    </form>
  );
}
