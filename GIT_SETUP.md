# Git Setup Instructions

This document provides instructions for setting up Git properly for this project.

## Initial Setup

1. **Clone the repository**

   ```bash
   git clone https://github.com/yourusername/dev-environment.git
   cd dev-environment
   ```

2. **Configure Git identity**

   ```bash
   git config user.name "Your Name"
   git config user.email "your.email@example.com"
   ```

3. **Configure Git hooks**

   ```bash
   # Make git hooks executable
   chmod +x .githooks/pre-commit
   
   # Set hooks path
   git config core.hooksPath .githooks
   ```

## Workflow Best Practices

### Branch Strategy

Follow the GitHub Flow branching strategy:

1. **Create a feature branch**

   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes and commit**

   ```bash
   git add .
   git commit -m "Descriptive commit message"
   ```

3. **Push changes to remote**

   ```bash
   git push -u origin feature/your-feature-name
   ```

4. **Open a Pull Request** on GitHub

5. **After review, merge** the PR into main

### Commit Message Guidelines

Follow the Conventional Commits specification for commit messages:

```
<type>(<scope>): <description>

[optional body]

[optional footer(s)]
```

Types:
- `feat`: A new feature
- `fix`: A bug fix
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance
- `test`: Adding missing tests or correcting existing tests
- `chore`: Changes to the build process or auxiliary tools

Examples:
```
feat(dashboard): add service health indicators
fix(flask): correct CORS configuration
docs(readme): update installation instructions
```

## Git LFS Setup

For large files, we use Git LFS (Large File Storage):

1. **Install Git LFS**

   ```bash
   # On macOS
   brew install git-lfs
   
   # On Ubuntu
   sudo apt-get install git-lfs
   
   # On Windows (with Chocolatey)
   choco install git-lfs
   ```

2. **Enable Git LFS**

   ```bash
   git lfs install
   ```

3. **Track specific file types**

   ```bash
   git lfs track "*.zip"
   git lfs track "*.jpg"
   git lfs track "*.png"
   ```

## Troubleshooting

### Line Ending Issues

If you encounter line ending issues between different operating systems:

```bash
# Configure Git to handle line endings
git config --global core.autocrlf input  # For Mac/Linux
git config --global core.autocrlf true   # For Windows
```

### Git Hooks Not Running

If git hooks are not running:

```bash
# Verify git hooks path
git config core.hooksPath

# Make sure hooks are executable
chmod +x .githooks/*
```

## Additional Git Configuration

### Useful Aliases

Set up helpful Git aliases:

```bash
git config --global alias.st status
git config --global alias.co checkout
git config --global alias.br branch
git config --global alias.ci commit
git config --global alias.unstage 'reset HEAD --'
git config --global alias.last 'log -1 HEAD'
git config --global alias.visual '!gitk'
```

### Enable Git Security Features

```bash
# Verify signatures
git config --global gpg.program gpg
git config --global commit.gpgsign true

# Safer force-pushing
git config --global push.default current
git config --global push.followTags true
```