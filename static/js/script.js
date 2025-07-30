document.addEventListener("DOMContentLoaded", function () {
  const videoInput = document.getElementById("videos");
  const videoHelpText = document.getElementById("video_help_text"); // Adicionei este elemento para feedback

  if (videoInput && videoHelpText) {
    // Garante que os elementos existam na página
    videoInput.addEventListener("change", function (event) {
      const files = event.target.files;
      const validFiles = [];
      let foundLargeVideo = false;

      // Função assíncrona para processar os arquivos sequencialmente
      async function processFiles() {
        for (const file of files) {
          // Verifica se o arquivo é um vídeo antes de tentar carregar metadados
          if (file.type.startsWith("video/")) {
            const videoURL = URL.createObjectURL(file);
            const video = document.createElement("video");
            video.preload = "metadata";

            await new Promise((resolve) => {
              video.onloadedmetadata = function () {
                URL.revokeObjectURL(videoURL);
                // Obtém a duração máxima do atributo de dados (data-max-duration)
                // ou usa um valor padrão se não estiver definido
                const maxDuration = parseInt(
                  videoInput.dataset.maxDuration || "20",
                  10
                );

                if (video.duration > maxDuration) {
                  alert(
                    `O vídeo "${file.name}" tem aproximadamente ${Math.round(
                      video.duration
                    )} segundos, excedendo o limite de ${maxDuration} segundos. Ele não será enviado.`
                  );
                  foundLargeVideo = true;
                } else {
                  validFiles.push(file);
                }
                resolve();
              };
              video.onerror = function () {
                console.error(
                  `Erro ao carregar metadados do vídeo: ${file.name}`
                );
                validFiles.push(file); // Se não conseguir carregar, adicione para não bloquear o upload
                resolve();
              };
              video.src = videoURL;
            });
          } else {
            // Se não for um vídeo, adicione-o diretamente à lista de arquivos válidos
            validFiles.push(file);
          }
        }

        // Cria um novo FileList com os arquivos válidos
        const dataTransfer = new DataTransfer();
        validFiles.forEach((file) => dataTransfer.items.add(file));
        videoInput.files = dataTransfer.files;

        // Atualiza o texto de ajuda visualmente
        const maxDuration = parseInt(
          videoInput.dataset.maxDuration || "20",
          10
        );
        if (foundLargeVideo) {
          videoHelpText.textContent = `Alguns vídeos foram removidos. Limite: ${maxDuration} segundos.`;
          videoHelpText.style.color = "red";
        } else {
          videoHelpText.textContent = `Vídeos com mais de ${maxDuration} segundos serão removidos.`;
          videoHelpText.style.color = "inherit"; // Volta à cor padrão
        }
      }

      processFiles();
    });
  }
});
