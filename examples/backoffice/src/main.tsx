import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import Layout from "./Layout";
import ArticleList from "./pages/ArticleList";
import ArticleForm from "./pages/ArticleForm";
import CategoryList from "./pages/CategoryList";
import UserList from "./pages/UserList";
import "./index.css";

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<Navigate to="/articles" replace />} />
            <Route path="/articles" element={<ArticleList />} />
            <Route path="/articles/new" element={<ArticleForm />} />
            <Route path="/articles/:id" element={<ArticleForm />} />
            <Route path="/categories" element={<CategoryList />} />
            <Route path="/users" element={<UserList />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
