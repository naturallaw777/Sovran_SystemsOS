# Contributing to Sovran Systems OS

First off, thank you for considering contributing to Sovran_SystemsOS! 🎉

## This GitHub Repo

The GitHub repository is the **development mirror** of Sovran_SystemsOS and serves as
its connection to the GitHub ecosystem. The **main, stable repository** is
self-hosted on the project's Gitea instance at
https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS
([`stable` branch](https://git.sovransystems.com/Sovran_Systems/Sovran_SystemsOS/src/branch/stable)),
as the ethos of Sovran_SystemsOS is self-sovereignty.

The workflow is:

1. Development happens on the `staging-dev` branch on Gitea, which the GitHub
   repository mirrors.
2. All activity in the GitHub repo — issues, pull requests, reviews, and
   testing — is done against the mirrored `staging-dev` code.
3. When changes are complete and tested, they are moved to the `stable` branch
   on the Gitea instance, which is the code used by released Sovran_SystemsOS
   builds.

Please note: the GitHub repo mirrors `staging-dev`, so it may contain new features
and code not yet in the `stable` branch on Gitea, and this code is not fully
tested.

Moreover, Sovran_SystemsOS has been improved with the help of AI. We have used Copilot and Arean.Ai to work through significant coding challenges and troubleshooting hurdles. We will continue to use AI to help keep Sovran_SystemsOS stable and maintained.

## How Can I Contribute?

### 🐛 Reporting Bugs
- Open an [Issue](https://github.com/naturallaw777/Sovran_SystemsOS/issues)
- Use a clear and descriptive title
- Describe the steps to reproduce the bug
- Include your OS version, hardware specs, and any relevant logs

### 💡 Suggesting Features
- Open an [Issue](https://github.com/naturallaw777/Sovran_SystemsOS/issues) with the tag `enhancement`
- Explain the feature and why it would be useful
- Be as detailed as possible

### 🔧 Submitting Code Changes

#### 1. Fork the Repository
Click the "Fork" button at the top right of the GitHub repository.

#### 2. Clone Your Fork
```bash
git clone https://github.com/YOUR_USERNAME/Sovran_SystemsOS.git
cd Sovran_SystemsOS
```

#### 3. Create a Feature Branch
```bash
git checkout -b feature/your-feature-name
```

#### 4. Make Your Changes
- Write clean, well-commented code
- Follow the existing code style and structure
- Test your changes thoroughly

#### 5. Commit Your Changes
```bash
git add .
git commit -m "Brief description of your changes"
```

#### 6. Push to Your Fork
```bash
git push origin feature/your-feature-name
```

#### 7. Open a Pull Request
- Go to the original repository on GitHub
- Click "New Pull Request"
- Select your fork and branch
- Provide a clear title and description of your changes
- Reference any related Issues (e.g., "Closes #12")

## Pull Request Guidelines

- **One PR per feature/fix.** Do not bundle unrelated changes.
- **Keep PRs small and focused.** Smaller PRs are easier to review and merge.
- **Write meaningful commit messages.**
- **Do not push directly to `main`.** Always use a feature branch and open a PR.
- **Be patient.** PRs will be reviewed as soon as possible.

## Code Style

- Follow the existing patterns in the codebase
- Comment your code where necessary
- Keep functions small and focused

## Code of Conduct

By participating in this project, you agree to be respectful and constructive.
We are building something meaningful — let's do it together with integrity.

