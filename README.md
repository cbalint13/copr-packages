# copr-packages
## Copr Package Automation

This repo is intended to automate release engineering within [RedHat/Fedora COPR](https://copr.fedorainfracloud.org) build services.

At current time the [automated actions](https://github.com/cbalint13/copr-packages/actions) drives the following COPR projects:
   * [Machine Learning](https://copr.fedorainfracloud.org/coprs/rezso/ML) related packages.
   * [Hardware Description Language Tools](https://copr.fedorainfracloud.org/coprs/rezso/HDL) related packages.
   * [Open source VLSI Tools](https://copr.fedorainfracloud.org/coprs/rezso/VLSI) related packages.
   * [Software Defined Radio](https://copr.fedorainfracloud.org/coprs/rezso/SDR) related packages.
   * [Mobile Communication](https://copr.fedorainfracloud.org/coprs/rezso/MOBILE) related packages.

----

### **Action Workflow:**
* Uses a **scheduled GITHUB service** within a simple Docker container.
* Remote copr **repo packages are parsed** against upstream scm sources (github, bitbucket, svn, etc).
* In case of **new upstream** changes a **new build** is initiated having updated **n-v-r, hashes, tags**.
* Incremental **release policy** of a package can be: *tag based* (latest stable) or *hash based* (latest edge).

### **N-V-R:**

* **HASH** based, *latest edge* stepping:

```
1.02-20211229.0.git48498af8
 |      |     |    |
 |      |     |    |__ hash of SCM (short version)
 |      |     |_______ package number (minor version)
 |      |_____________ date of SCM commit
 |____________________ upstream version
```

```
[abc.spec]
%global pkgvers 0
%global scdate0 20211229
%global schash0 48498af8189ef321ee876065d8947875cf711294
%global branch0 master
%global source0 https://github.com/berkeley-abc/abc.git
...
Version:        1.02
Release:        %{scdate0}.%{pkgvers}.git%{sshort0}
...
```

* **TAG** based, *latest stable* stepping:

```
2.10.0-20220915.0
 |        |     |
 |        |     |_______ package number (minor version)
 |        |_____________ date of TAG release
 |______________________ upstream version
```
```
[cutlass.spec]
%global pkgvers 0
%global scdate0 20220915
%global sctags0 v2.10.0
%global source0 https://github.com/NVIDIA/cutlass.git
...
Version:        2.10.0
Release:        %{scdate0}.%{pkgvers}.cu%{vcu_maj}_%{vcu_min}%{?dist}
...
```

### **Security:**
* **Root of trust** is the very [RedHat/Fedora COPR](https://copr.fedorainfracloud.org) service.
* **Transparency** of builds are **guaranteed** by detailed **end-to-end logs** for all build processes.
* There are **no static tarballs** but links to SCM sources that are **fetched from upstream** at build time.
* Built packages on COPR service are **cryptographically signed** thus **certifies their origin** from COPR cloud.

### **Principles:**
Keep it simple !

