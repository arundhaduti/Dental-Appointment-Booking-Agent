import axios from "axios";

const API = axios.create({
  baseURL: "http://localhost:8000",
});

export const sendMessage = (message) => API.post("/chat", { message });

export const resetChat = () => API.post("/reset");
