import React, { createContext, useContext, useState, useEffect } from 'react';
import { User, UserRole } from '../types';
import { authService } from '../services/authService';

interface AuthContextType {
  user: User | null;
  token: string | null;
  role: UserRole | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  login: (token: string, user: User, refreshToken?: string) => void;
  logout: () => Promise<void>;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<User | null>(() => {
    const saved = localStorage.getItem('civicfix_user');
    return saved ? JSON.parse(saved) : null;
  });
  const [token, setToken] = useState<string | null>(() => {
    return localStorage.getItem('civicfix_token');
  });
  const [isLoading, setIsLoading] = useState<boolean>(true);

  useEffect(() => {
    const initAuth = async () => {
      const savedToken = localStorage.getItem('civicfix_token');
      if (savedToken) {
        try {
          const freshUser = await authService.getCurrentUser();
          setUser(freshUser);
          localStorage.setItem('civicfix_user', JSON.stringify(freshUser));
        } catch {
          setUser(null);
          setToken(null);
          localStorage.removeItem('civicfix_token');
          localStorage.removeItem('civicfix_user');
        }
      }
      setIsLoading(false);
    };
    initAuth();
  }, []);

  const login = (newToken: string, newUser: User, refreshToken?: string) => {
    setToken(newToken);
    setUser(newUser);
    localStorage.setItem('civicfix_token', newToken);
    localStorage.setItem('civicfix_user', JSON.stringify(newUser));
    if (refreshToken) {
      localStorage.setItem('civicfix_refresh_token', refreshToken);
    }
  };

  const logout = async () => {
    try {
      await authService.logout();
    } catch {
      // ignore
    } finally {
      setToken(null);
      setUser(null);
      localStorage.removeItem('civicfix_token');
      localStorage.removeItem('civicfix_refresh_token');
      localStorage.removeItem('civicfix_user');
    }
  };

  const refreshUser = async () => {
    if (token) {
      try {
        const freshUser = await authService.getCurrentUser();
        setUser(freshUser);
        localStorage.setItem('civicfix_user', JSON.stringify(freshUser));
      } catch {
        // ignore
      }
    }
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        token,
        role: user ? user.role : null,
        isAuthenticated: !!token && !!user,
        isLoading,
        login,
        logout,
        refreshUser,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider');
  }
  return context;
};

